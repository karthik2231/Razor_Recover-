"""Shared pytest fixtures."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_env(monkeypatch, tmp_path):
    db_path = tmp_path / "recovery_cases.db"
    audit_path = tmp_path / "audit_log.jsonl"

    monkeypatch.setenv("RECOVERY_DB_PATH", str(db_path))
    monkeypatch.setenv("REVIEW_API_TOKEN", "test-review-token")
    monkeypatch.setenv("WEBHOOK_SECRET", "whsec_test_secret")
    monkeypatch.setenv("ENABLE_AUTO_RECOVERY", "false")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_fake")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "fake_secret")
    monkeypatch.setenv("EXECUTION_LIMIT_RUPEES", "5000")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")

    import backend.app.services.audit_service as audit_service

    monkeypatch.setattr(audit_service, "AUDIT_FILE", audit_path)

    return {
        "db_path": db_path,
        "audit_path": audit_path,
        "token": "test-review-token",
        "webhook_secret": "whsec_test_secret",
    }


@pytest.fixture
def client(temp_env):
    from backend.app.main import app

    return TestClient(app)


def sign_webhook(payload: dict, secret: str, event_id: str = "evt_test_1") -> tuple[bytes, dict]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = __import__("hmac").new(
        secret.encode(), body, __import__("hashlib").sha256
    ).hexdigest()
    headers = {
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": event_id,
        "Content-Type": "application/json",
    }
    return body, headers


def post_webhook(client, payload: dict, secret: str, event_id: str = "evt_test_1"):
    body, headers = sign_webhook(payload, secret, event_id)
    return client.post("/webhook/razorpay", content=body, headers=headers)


def auth_headers(token: str) -> dict:
    return {"X-Review-Token": token}


def sample_failed_payload(payment_id: str = "pay_fail_1", order_id: str = "order_1") -> dict:
    return {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 50000,
                    "method": "upi",
                    "contact": "8610169138",
                    "email": "demo@test.com",
                    "error_reason": "bank_timeout",
                }
            }
        },
    }


def sample_link_eligible_payload(
    payment_id: str = "pay_link",
    order_id: str = "order_link",
) -> dict:
    """Failed payment that yields CREATE_PAYMENT_LINK + policy ALLOW."""
    return {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 250000,
                    "method": "upi",
                    "contact": "8610169138",
                    "email": "demo@test.com",
                    "error_reason": "insufficient_funds",
                }
            }
        },
    }


def sample_captured_payload(
    payment_id: str = "pay_cap_1",
    order_id: str = "order_1",
    amount: int = 50000,
) -> dict:
    return {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount,
                }
            }
        },
    }
