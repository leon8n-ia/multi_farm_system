"""
FastAPI Access Server for subscription-based Google Drive access.
"""
import os
import json
import hmac
import hashlib
import secrets
import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from dotenv import load_dotenv

from database import (
    init_db,
    get_subscription_by_token,
    get_subscription_by_dodo_id,
    create_subscription,
    update_subscription_status,
    update_subscription_expiry,
)

load_dotenv()

# Environment variables
DODO_PAYMENTS_API_KEY = os.getenv("DODO_PAYMENTS_API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "")

# Google Drive folder IDs for each farm type
DEFAULT_GOOGLE_DRIVE_FOLDER_IDS = {
    "data_cleaning": "1qjVs8bQ6XzuSzuMin1fvR82wA-7NZza9",
    "auto_reports": "1tcd4KREz_ABMzORmg_a9s5BXvuZHsjxD",
    "product_listing": "1P7SCGJ0m8J-wLg678eZWkvYfcm5y5v7g",
    "monetized_content": "1GO03fu8aM0nXNYxNBOSFb4ESkWwgidcg",
    "react_nextjs": "19kIvsTU7O7ReSGrBOaAoBIkZ3OZmXXwL",
    "devops_cloud": "1A69s783nK31hGAqtjb8yoqoHKU-kG1Ic",
    "mobile_dev": "1o9Xx3yA2E6v_rcucaG14mIuXM_r-R9Ub"
}
GOOGLE_DRIVE_FOLDER_IDS = json.loads(os.getenv("GOOGLE_DRIVE_FOLDER_IDS", json.dumps(DEFAULT_GOOGLE_DRIVE_FOLDER_IDS)))
SELF_URL = os.getenv("SELF_URL", "http://localhost:8000")
PING_INTERVAL_SECONDS = 300  # 5 minutes

# Dodo Product ID to Farm Type mapping
DEFAULT_DODO_PRODUCT_MAP = {
    "pdt_0NcCKncWZl6oDekJpv4tA": "data_cleaning",
    "pdt_0NcCMQENFmyGx6Xm9FKJQ": "auto_reports",
    "pdt_0NcCOy6cUf8AcLvWYzAxF": "product_listing",
    "pdt_0NcCPsEPr8gorZXNZBDJz": "monetized_content",
    "pdt_0NcCQqoSUsK5laXLdaWXX": "react_nextjs",
    "pdt_0NcCRa16qmakkjcukuT0B": "devops_cloud",
    "pdt_0NcCSCR94KtfQU0HptlG7": "mobile_dev"
}
DODO_PRODUCT_MAP = json.loads(os.getenv("DODO_PRODUCT_MAP", json.dumps(DEFAULT_DODO_PRODUCT_MAP)))


async def self_ping_task():
    """Background task to ping /health every 5 minutes to prevent Render sleep."""
    while True:
        await asyncio.sleep(PING_INTERVAL_SECONDS)
        try:
            requests.get(f"{SELF_URL}/health", timeout=10)
        except Exception:
            pass  # Ignore errors, just keep trying


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    init_db()
    # Start self-ping task
    ping_task = asyncio.create_task(self_ping_task())
    yield
    # Shutdown
    ping_task.cancel()
    try:
        await ping_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Access Server",
    description="Subscription-based access to Google Drive resources",
    version="1.0.0",
    lifespan=lifespan,
)


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Dodo webhook signature."""
    if not SECRET_KEY:
        return True  # Skip verification if no secret configured
    expected = hmac.new(
        SECRET_KEY.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def generate_access_token() -> str:
    """Generate a secure random access token."""
    return secrets.token_urlsafe(32)


def get_drive_link(farm_type: str) -> Optional[str]:
    """Get Google Drive folder link for a farm type."""
    folder_id = GOOGLE_DRIVE_FOLDER_IDS.get(farm_type)
    if folder_id:
        return f"https://drive.google.com/drive/folders/{folder_id}"
    return None


def get_farm_type_from_product(product_id: str) -> str:
    """Get farm type from Dodo product ID."""
    return DODO_PRODUCT_MAP.get(product_id, "default")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/access/{token}")
async def access_resource(token: str):
    """
    Verify token has active subscription and redirect to Google Drive.
    """
    subscription = get_subscription_by_token(token)

    if not subscription:
        raise HTTPException(status_code=404, detail="Token not found")

    if subscription["status"] != "active":
        raise HTTPException(
            status_code=403,
            detail=f"Subscription is {subscription['status']}"
        )

    # Check expiration
    if subscription["expires_at"]:
        expires_at = datetime.fromisoformat(subscription["expires_at"])
        if datetime.utcnow() > expires_at:
            update_subscription_status(
                subscription["dodo_subscription_id"],
                "expired"
            )
            raise HTTPException(status_code=403, detail="Subscription has expired")

    # Get Google Drive link
    drive_link = get_drive_link(subscription["farm_type"])
    if not drive_link:
        raise HTTPException(
            status_code=500,
            detail="Drive folder not configured for this farm type"
        )

    return RedirectResponse(url=drive_link, status_code=302)


@app.post("/webhook/dodo")
async def dodo_webhook(request: Request):
    """
    Handle Dodo Payments webhook events.

    Expected events:
    - subscription.created
    - subscription.active
    - subscription.cancelled
    - subscription.expired
    - payment.succeeded
    - payment.failed
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify signature
    signature = request.headers.get("X-Dodo-Signature", "")
    if not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type", "")
    data = payload.get("data", {})

    if event_type == "subscription.created":
        # Create new subscription with access token
        subscription_id = data.get("subscription_id")
        email = data.get("customer", {}).get("email", "")
        product_id = data.get("product_id", "")
        # Get farm_type from product_id, fallback to metadata, then default
        farm_type = get_farm_type_from_product(product_id)
        if farm_type == "default":
            farm_type = data.get("metadata", {}).get("farm_type", "default")
        expires_at = data.get("current_period_end")

        # Check if subscription already exists
        existing = get_subscription_by_dodo_id(subscription_id)
        if not existing:
            token = generate_access_token()
            create_subscription(
                token=token,
                farm_type=farm_type,
                dodo_subscription_id=subscription_id,
                email=email,
                expires_at=expires_at
            )
            # TODO: Send email with access token to user

    elif event_type == "subscription.active":
        subscription_id = data.get("subscription_id")
        update_subscription_status(subscription_id, "active")
        expires_at = data.get("current_period_end")
        if expires_at:
            update_subscription_expiry(subscription_id, expires_at)

    elif event_type == "subscription.cancelled":
        subscription_id = data.get("subscription_id")
        update_subscription_status(subscription_id, "cancelled")

    elif event_type == "subscription.expired":
        subscription_id = data.get("subscription_id")
        update_subscription_status(subscription_id, "expired")

    elif event_type == "payment.succeeded":
        subscription_id = data.get("subscription_id")
        if subscription_id:
            update_subscription_status(subscription_id, "active")
            expires_at = data.get("period_end")
            if expires_at:
                update_subscription_expiry(subscription_id, expires_at)

    elif event_type == "payment.failed":
        subscription_id = data.get("subscription_id")
        if subscription_id:
            update_subscription_status(subscription_id, "payment_failed")

    return JSONResponse({"received": True})


@app.get("/subscription/{token}/status")
async def get_subscription_status(token: str):
    """Get subscription status by token (for debugging/admin)."""
    subscription = get_subscription_by_token(token)
    if not subscription:
        raise HTTPException(status_code=404, detail="Token not found")

    return {
        "farm_type": subscription["farm_type"],
        "status": subscription["status"],
        "created_at": subscription["created_at"],
        "expires_at": subscription["expires_at"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
