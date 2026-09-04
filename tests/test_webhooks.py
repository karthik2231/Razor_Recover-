"""Webhook endpoint tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from tests.conftest import (
    auth_headers,
    post_webhook,
    sample_failed_payload,
    sample_link_eligible_payload,
    sign_webhook,
)


def test_valid_webhook_signature_accepted(client, temp_env):
    payload = sample_failed_payload()
    response = post_webhook(client, payload, temp_env["webhook_secret"], "evt_ok")
    assert response.status_code == 200
    assert response.json()["status"] == "received"


def test_invalid_webhook_signature_rejected(client, temp_env):
    payload = sample_failed_payload()
    body, headers = sign_webhook(payload, temp_env["webhook_secret"], "evt_bad")
    headers["X-Razorpay-Signature"] = "bad"
    response = client.post("/webhook/razorpay", content=body, headers=headers)
    assert response.status_code == 400


def test_missing_webhook_signature_rejected(client, temp_env):
    payload = sample_failed_payload()
    body, _ = sign_webhook(payload, temp_env["webhook_secret"], "evt_missing")
    response = client.post("/webhook/razorpay", content=body)
    assert response.status_code == 400


def test_invalid_json_webhook_rejected(client, temp_env):
    body = b"not-json"
    signature = __import__("hmac").new(
        temp_env["webhook_secret"].encode(), body, __import__("hashlib").sha256
    ).hexdigest()
    response = client.post(
        "/webhook/razorpay",
        content=body,
        headers={
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": "evt_json",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400


def test_unsupported_webhook_event_ignored(client, temp_env):
    payload = {"event": "subscription.charged", "payload": {}}
    response = post_webhook(client, payload, temp_env["webhook_secret"], "evt_unsupported")
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_duplicate_webhook_is_idempotent(client, temp_env):
    payload = sample_failed_payload(payment_id="pay_dup", order_id="order_dup")
    first = post_webhook(client, payload, temp_env["webhook_secret"], "evt_dup")
    second = post_webhook(client, payload, temp_env["webhook_secret"], "evt_dup")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"


def test_failed_payment_creates_recovery_case(client, temp_env):
    payload = sample_failed_payload(payment_id="pay_case", order_id="order_case")
    post_webhook(client, payload, temp_env["webhook_secret"], "evt_case")

    cases = client.get("/webhook-cases", headers=auth_headers(temp_env["token"]))
    assert cases.status_code == 200
    data = cases.json()
    assert data["count"] == 1
    assert data["cases"][0]["case_id"] == "order_case"
    assert data["cases"][0]["recovery_score"] is not None
    assert data["cases"][0]["policy_decision"] in {"ALLOW", "REVIEW", "DENY"}


def test_score_and_policy_saved(client, temp_env):
    from webhook_recovery import get_case

    payload = sample_failed_payload(payment_id="pay_score", order_id="order_score")
    post_webhook(client, payload, temp_env["webhook_secret"], "evt_score")

    case = get_case("order_score")
    assert case is not None
    assert case["recovery_score"] is not None
    assert case["recommended_action"] is not None
    assert case["policy_decision"] is not None


def test_razorpay_insufficient_fund_error_is_normalized(client, temp_env):
    payload = sample_link_eligible_payload(
        payment_id="pay_insufficient", order_id="order_insufficient"
    )
    payload["payload"]["payment"]["entity"]["error_reason"] = "insufficient_fund"
    post_webhook(client, payload, temp_env["webhook_secret"], "evt_insufficient")

    from webhook_recovery import get_case

    case = get_case("order_insufficient")
    assert case["failure_reason"] == "insufficient_funds"
    assert case["recommended_action"] == "CREATE_PAYMENT_LINK"
    assert case["policy_decision"] == "ALLOW"


def test_developer_simulation_uses_the_existing_recovery_pipeline(
    client, temp_env, monkeypatch
):
    monkeypatch.setenv("ENABLE_DEVELOPER_SIMULATION", "true")
    response = client.post(
        "/test/simulate-failure",
        json={"amount": 450, "failure_reason": "payment_failed"},
        headers=auth_headers(temp_env["token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["simulated"] is True
    assert body["source"] == "simulation"

    cases = client.get("/webhook-cases", headers=auth_headers(temp_env["token"])).json()
    assert cases["cases"][0]["source"] == "simulation"


@patch("backend.app.routes.razorpay.create_test_payment_link")
def test_normal_payment_link_uses_test_mode_backend_endpoint(
    mock_create, client, temp_env
):
    mock_create.return_value = (
        "TXN_TEST_123",
        {"id": "plink_123", "short_url": "https://rzp.io/test", "reference_id": "TXN_TEST_123"},
    )
    response = client.post(
        "/payments/normal-link",
        json={
            "amount": 500,
            "customer_name": "Demo Customer",
            "customer_email": "demo@example.test",
            "customer_contact": "8610169138",
        },
        headers=auth_headers(temp_env["token"]),
    )

    assert response.status_code == 200
    assert response.json()["payment_type"] == "initial_normal_payment"
    assert response.json()["payment_link_url"] == "https://rzp.io/test"


@patch("backend.app.routes.razorpay.fetch_test_payment_link")
def test_recovery_link_can_be_retrieved_after_creation(
    mock_fetch, client, temp_env
):
    from webhook_recovery import _connect

    with _connect() as connection:
        connection.execute(
            """INSERT INTO recovery_cases (
                case_id, payment_id, payment_status, amount_paise,
                lifecycle_status, recovery_link_id
            ) VALUES (?, ?, 'failed', ?, 'LINK_CREATED', ?)""",
            ("case_link", "pay_link", 50000, "plink_123"),
        )
    mock_fetch.return_value = {"short_url": "https://rzp.io/recovery", "status": "created"}

    response = client.get(
        "/webhook-cases/case_link/payment-link",
        headers=auth_headers(temp_env["token"]),
    )
    assert response.status_code == 200
    assert response.json()["payment_link_url"] == "https://rzp.io/recovery"


@patch("backend.app.routes.razorpay.fetch_test_payment")
@patch("backend.app.routes.razorpay.fetch_test_payment_link")
def test_recovery_payment_can_be_reconciled_after_missed_webhook(
    mock_link, mock_payment, client, temp_env
):
    from webhook_recovery import _connect

    with _connect() as connection:
        connection.execute(
            """INSERT INTO recovery_cases (
                case_id, payment_id, payment_status, amount_paise,
                lifecycle_status, recovery_link_id, recovery_link_reference_id
            ) VALUES (?, ?, 'failed', ?, 'LINK_CREATED', ?, ?)""",
            ("case_sync", "pay_original", 50000, "plink_sync", "RECOVERY_case_sync"),
        )
    mock_link.return_value = {"status": "paid", "payments": [{"payment_id": "pay_recovery", "status": "captured"}], "reference_id": "RECOVERY_case_sync"}
    mock_payment.return_value = {"id": "pay_recovery", "amount": 50000, "notes": {"reference_id": "RECOVERY_case_sync"}}

    response = client.post(
        "/webhook-cases/case_sync/sync-payment",
        headers=auth_headers(temp_env["token"]),
    )
    assert response.status_code == 200
    assert response.json()["synced"] is True
