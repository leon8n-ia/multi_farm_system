"""
SQLite database module for subscription management.
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

DATABASE_PATH = os.getenv("DATABASE_PATH", "subscriptions.db")


def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database with required tables."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                token TEXT PRIMARY KEY,
                farm_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                dodo_subscription_id TEXT,
                paypal_subscription_id TEXT,
                email TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dodo_subscription_id
            ON subscriptions(dodo_subscription_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_paypal_subscription_id
            ON subscriptions(paypal_subscription_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_email
            ON subscriptions(email)
        """)
        # Migration: add paypal_subscription_id column if missing
        cursor = conn.execute("PRAGMA table_info(subscriptions)")
        columns = [row[1] for row in cursor.fetchall()]
        if "paypal_subscription_id" not in columns:
            conn.execute(
                "ALTER TABLE subscriptions ADD COLUMN paypal_subscription_id TEXT"
            )


def get_subscription_by_token(token: str) -> Optional[dict]:
    """Get a subscription by its access token."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM subscriptions WHERE token = ?",
            (token,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_subscription_by_dodo_id(dodo_subscription_id: str) -> Optional[dict]:
    """Get a subscription by Dodo subscription ID."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM subscriptions WHERE dodo_subscription_id = ?",
            (dodo_subscription_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def create_subscription(
    token: str,
    farm_type: str,
    dodo_subscription_id: str,
    email: str,
    expires_at: Optional[str] = None
) -> dict:
    """Create a new subscription."""
    created_at = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO subscriptions
            (token, farm_type, status, dodo_subscription_id, email, created_at, expires_at)
            VALUES (?, ?, 'active', ?, ?, ?, ?)
        """, (token, farm_type, dodo_subscription_id, email, created_at, expires_at))
    return get_subscription_by_token(token)


def update_subscription_status(dodo_subscription_id: str, status: str) -> bool:
    """Update subscription status by Dodo subscription ID."""
    with get_db() as conn:
        cursor = conn.execute("""
            UPDATE subscriptions
            SET status = ?
            WHERE dodo_subscription_id = ?
        """, (status, dodo_subscription_id))
        return cursor.rowcount > 0


def update_subscription_expiry(dodo_subscription_id: str, expires_at: str) -> bool:
    """Update subscription expiry date."""
    with get_db() as conn:
        cursor = conn.execute("""
            UPDATE subscriptions
            SET expires_at = ?
            WHERE dodo_subscription_id = ?
        """, (expires_at, dodo_subscription_id))
        return cursor.rowcount > 0


# PayPal-specific functions

def get_subscription_by_paypal_id(paypal_subscription_id: str) -> Optional[dict]:
    """Get a subscription by PayPal subscription ID."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM subscriptions WHERE paypal_subscription_id = ?",
            (paypal_subscription_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def create_paypal_subscription(
    token: str,
    farm_type: str,
    paypal_subscription_id: str,
    email: str,
    expires_at: Optional[str] = None
) -> Optional[dict]:
    """Create a new subscription from PayPal."""
    created_at = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO subscriptions
            (token, farm_type, status, paypal_subscription_id, email, created_at, expires_at)
            VALUES (?, ?, 'active', ?, ?, ?, ?)
        """, (token, farm_type, paypal_subscription_id, email, created_at, expires_at))
    return get_subscription_by_token(token)


def update_paypal_subscription_status(paypal_subscription_id: str, status: str) -> bool:
    """Update subscription status by PayPal subscription ID."""
    with get_db() as conn:
        cursor = conn.execute("""
            UPDATE subscriptions
            SET status = ?
            WHERE paypal_subscription_id = ?
        """, (status, paypal_subscription_id))
        return cursor.rowcount > 0


def update_paypal_subscription_expiry(paypal_subscription_id: str, expires_at: str) -> bool:
    """Update subscription expiry date by PayPal subscription ID."""
    with get_db() as conn:
        cursor = conn.execute("""
            UPDATE subscriptions
            SET expires_at = ?
            WHERE paypal_subscription_id = ?
        """, (expires_at, paypal_subscription_id))
        return cursor.rowcount > 0
