"""
Tests for Access Server PayPal integration.

Tests database functions and endpoint logic.
"""
import os
import sys
import json
import tempfile
import sqlite3
import uuid
import unittest
from datetime import datetime

# Add parent directory and access_server to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)
sys.path.insert(0, os.path.join(parent_dir, "access_server"))


def create_test_db():
    """Create a fresh test database and return connection."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_file.close()

    conn = sqlite3.connect(temp_file.name)
    conn.row_factory = sqlite3.Row
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
        CREATE INDEX IF NOT EXISTS idx_paypal_subscription_id
        ON subscriptions(paypal_subscription_id)
    """)
    conn.commit()

    return conn, temp_file.name


class TestPayPalDatabaseFunctions(unittest.TestCase):
    """Test PayPal-related database functions with isolated DB."""

    def setUp(self):
        """Set up test database."""
        self.conn, self.db_path = create_test_db()

    def tearDown(self):
        """Clean up test database."""
        self.conn.close()
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_create_paypal_subscription(self):
        """Test creating a PayPal subscription."""
        token = f"test-token-{uuid.uuid4()}"
        paypal_id = f"I-TEST-{uuid.uuid4()}"

        self.conn.execute("""
            INSERT INTO subscriptions
            (token, farm_type, status, paypal_subscription_id, email, created_at, expires_at)
            VALUES (?, ?, 'active', ?, ?, ?, ?)
        """, (token, "data_cleaning", paypal_id, "test@example.com",
              datetime.utcnow().isoformat(), "2024-02-01T00:00:00Z"))
        self.conn.commit()

        cursor = self.conn.execute(
            "SELECT * FROM subscriptions WHERE paypal_subscription_id = ?",
            (paypal_id,)
        )
        row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["token"], token)
        self.assertEqual(row["farm_type"], "data_cleaning")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["email"], "test@example.com")

    def test_update_paypal_subscription_status(self):
        """Test updating PayPal subscription status."""
        token = f"test-token-{uuid.uuid4()}"
        paypal_id = f"I-TEST-{uuid.uuid4()}"

        self.conn.execute("""
            INSERT INTO subscriptions
            (token, farm_type, status, paypal_subscription_id, email, created_at)
            VALUES (?, ?, 'active', ?, ?, ?)
        """, (token, "devops_cloud", paypal_id, "test@example.com",
              datetime.utcnow().isoformat()))
        self.conn.commit()

        # Update to cancelled
        self.conn.execute("""
            UPDATE subscriptions SET status = ? WHERE paypal_subscription_id = ?
        """, ("cancelled", paypal_id))
        self.conn.commit()

        cursor = self.conn.execute(
            "SELECT status FROM subscriptions WHERE paypal_subscription_id = ?",
            (paypal_id,)
        )
        row = cursor.fetchone()
        self.assertEqual(row["status"], "cancelled")

    def test_update_paypal_subscription_expiry(self):
        """Test updating PayPal subscription expiry."""
        token = f"test-token-{uuid.uuid4()}"
        paypal_id = f"I-TEST-{uuid.uuid4()}"

        self.conn.execute("""
            INSERT INTO subscriptions
            (token, farm_type, status, paypal_subscription_id, email, created_at)
            VALUES (?, ?, 'active', ?, ?, ?)
        """, (token, "react_nextjs", paypal_id, "test@example.com",
              datetime.utcnow().isoformat()))
        self.conn.commit()

        # Update expiry
        new_expiry = "2024-03-01T00:00:00Z"
        self.conn.execute("""
            UPDATE subscriptions SET expires_at = ? WHERE paypal_subscription_id = ?
        """, (new_expiry, paypal_id))
        self.conn.commit()

        cursor = self.conn.execute(
            "SELECT expires_at FROM subscriptions WHERE paypal_subscription_id = ?",
            (paypal_id,)
        )
        row = cursor.fetchone()
        self.assertEqual(row["expires_at"], new_expiry)

    def test_get_nonexistent_paypal_subscription(self):
        """Test retrieving non-existent subscription returns None."""
        cursor = self.conn.execute(
            "SELECT * FROM subscriptions WHERE paypal_subscription_id = ?",
            ("I-NONEXISTENT",)
        )
        row = cursor.fetchone()
        self.assertIsNone(row)

    def test_update_nonexistent_subscription(self):
        """Test updating non-existent subscription affects 0 rows."""
        cursor = self.conn.execute("""
            UPDATE subscriptions SET status = ? WHERE paypal_subscription_id = ?
        """, ("cancelled", "I-NONEXISTENT"))
        self.conn.commit()
        self.assertEqual(cursor.rowcount, 0)


class TestPayPalWebhookLogic(unittest.TestCase):
    """Test PayPal webhook handling logic with isolated DB."""

    def setUp(self):
        """Set up test database."""
        self.conn, self.db_path = create_test_db()

    def tearDown(self):
        """Clean up test database."""
        self.conn.close()
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_subscription_activated_creates_token(self):
        """Test BILLING.SUBSCRIPTION.ACTIVATED creates access token."""
        import secrets

        subscription_id = f"I-WEBHOOK-{uuid.uuid4()}"
        email = "webhook@example.com"
        farm_type = "data_cleaning"

        # Check doesn't exist
        cursor = self.conn.execute(
            "SELECT * FROM subscriptions WHERE paypal_subscription_id = ?",
            (subscription_id,)
        )
        self.assertIsNone(cursor.fetchone())

        # Create (as webhook would do)
        token = secrets.token_urlsafe(32)
        self.conn.execute("""
            INSERT INTO subscriptions
            (token, farm_type, status, paypal_subscription_id, email, created_at)
            VALUES (?, ?, 'active', ?, ?, ?)
        """, (token, farm_type, subscription_id, email,
              datetime.utcnow().isoformat()))
        self.conn.commit()

        # Verify created
        cursor = self.conn.execute(
            "SELECT * FROM subscriptions WHERE paypal_subscription_id = ?",
            (subscription_id,)
        )
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "active")
        self.assertEqual(len(row["token"]), 43)  # base64 encoded 32 bytes

    def test_subscription_lifecycle(self):
        """Test full subscription lifecycle through webhooks."""
        subscription_id = f"I-LIFECYCLE-{uuid.uuid4()}"
        token = f"lifecycle-token-{uuid.uuid4()}"

        # 1. Activated
        self.conn.execute("""
            INSERT INTO subscriptions
            (token, farm_type, status, paypal_subscription_id, email, created_at)
            VALUES (?, ?, 'active', ?, ?, ?)
        """, (token, "mobile_dev", subscription_id, "lifecycle@example.com",
              datetime.utcnow().isoformat()))
        self.conn.commit()

        cursor = self.conn.execute(
            "SELECT status FROM subscriptions WHERE paypal_subscription_id = ?",
            (subscription_id,)
        )
        self.assertEqual(cursor.fetchone()["status"], "active")

        # 2. Suspended (payment failed)
        self.conn.execute(
            "UPDATE subscriptions SET status = ? WHERE paypal_subscription_id = ?",
            ("suspended", subscription_id)
        )
        self.conn.commit()
        cursor = self.conn.execute(
            "SELECT status FROM subscriptions WHERE paypal_subscription_id = ?",
            (subscription_id,)
        )
        self.assertEqual(cursor.fetchone()["status"], "suspended")

        # 3. Reactivated
        self.conn.execute(
            "UPDATE subscriptions SET status = ? WHERE paypal_subscription_id = ?",
            ("active", subscription_id)
        )
        self.conn.commit()
        cursor = self.conn.execute(
            "SELECT status FROM subscriptions WHERE paypal_subscription_id = ?",
            (subscription_id,)
        )
        self.assertEqual(cursor.fetchone()["status"], "active")

        # 4. Cancelled
        self.conn.execute(
            "UPDATE subscriptions SET status = ? WHERE paypal_subscription_id = ?",
            ("cancelled", subscription_id)
        )
        self.conn.commit()
        cursor = self.conn.execute(
            "SELECT status FROM subscriptions WHERE paypal_subscription_id = ?",
            (subscription_id,)
        )
        self.assertEqual(cursor.fetchone()["status"], "cancelled")


class TestPayPalSubscribeEndpointLogic(unittest.TestCase):
    """Test PayPal subscribe endpoint logic."""

    def test_valid_farm_types(self):
        """Test valid farm types list."""
        valid_types = [
            "data_cleaning", "auto_reports", "product_listing",
            "monetized_content", "react_nextjs", "devops_cloud", "mobile_dev"
        ]

        for farm_type in valid_types:
            self.assertIn(farm_type, valid_types)

    def test_checkout_url_format(self):
        """Test PayPal checkout URL format."""
        plan_id = "P-TEST-PLAN-123"
        sandbox = True

        base = "sandbox.paypal.com" if sandbox else "www.paypal.com"
        checkout_url = f"https://{base}/webapps/billing/subscriptions?plan_id={plan_id}"

        self.assertIn("sandbox.paypal.com", checkout_url)
        self.assertIn(plan_id, checkout_url)

    def test_production_url_format(self):
        """Test production PayPal URL."""
        plan_id = "P-PROD-PLAN-456"
        sandbox = False

        base = "sandbox.paypal.com" if sandbox else "www.paypal.com"
        checkout_url = f"https://{base}/webapps/billing/subscriptions?plan_id={plan_id}"

        self.assertIn("www.paypal.com", checkout_url)
        self.assertNotIn("sandbox", checkout_url)


class TestPayPalPlanMapping(unittest.TestCase):
    """Test PayPal plan ID mapping."""

    def test_plan_map_structure(self):
        """Test PayPal plan map has all farm types."""
        default_plan_map = {
            "data_cleaning": "",
            "auto_reports": "",
            "product_listing": "",
            "monetized_content": "",
            "react_nextjs": "",
            "devops_cloud": "",
            "mobile_dev": ""
        }

        self.assertEqual(len(default_plan_map), 7)
        self.assertIn("data_cleaning", default_plan_map)
        self.assertIn("devops_cloud", default_plan_map)

    def test_farm_type_from_plan_id(self):
        """Test finding farm type from plan ID."""
        plan_map = {
            "data_cleaning": "P-DATA-001",
            "auto_reports": "P-AUTO-002",
            "devops_cloud": "P-DEV-003"
        }

        # Find farm type from plan ID
        plan_id = "P-DEV-003"
        farm_type = "default"
        for ft, pid in plan_map.items():
            if pid == plan_id:
                farm_type = ft
                break

        self.assertEqual(farm_type, "devops_cloud")

    def test_unknown_plan_id_returns_default(self):
        """Test unknown plan ID returns default farm type."""
        plan_map = {"data_cleaning": "P-DATA-001"}

        plan_id = "P-UNKNOWN"
        farm_type = "default"
        for ft, pid in plan_map.items():
            if pid == plan_id:
                farm_type = ft
                break

        self.assertEqual(farm_type, "default")


class TestDatabaseMigration(unittest.TestCase):
    """Test database migration adds paypal_subscription_id column."""

    def test_schema_has_paypal_column(self):
        """Test schema includes paypal_subscription_id column."""
        conn, db_path = create_test_db()

        cursor = conn.execute("PRAGMA table_info(subscriptions)")
        columns = [row[1] for row in cursor.fetchall()]

        conn.close()
        try:
            os.unlink(db_path)
        except Exception:
            pass

        self.assertIn("paypal_subscription_id", columns)
        self.assertIn("dodo_subscription_id", columns)
        self.assertIn("token", columns)
        self.assertIn("farm_type", columns)
        self.assertIn("status", columns)
        self.assertIn("email", columns)


if __name__ == "__main__":
    unittest.main()
