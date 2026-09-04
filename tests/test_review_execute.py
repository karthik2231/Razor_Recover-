"""Reviewer authentication and AI auto-approval workflow tests."""

from __future__ import annotations

from unittest.mock import patch

from tests.conftest import (
    auth_headers,
    post_webhook,
    sample_captured_payload,
    sample_failed_payload,
    sample_link_eligible_payload,
)


def test_reviewer_endpoint_rejects_missing_token(
    client,
    temp_env,
):
    response = client.get(
        "/webhook-cases"
    )

    assert response.status_code == 401


def test_reviewer_endpoint_rejects_invalid_token(
    client,
    temp_env,
):
    response = client.get(
        "/webhook-cases",
        headers={
            "X-Review-Token": "wrong",
        },
    )

    assert response.status_code == 401


def test_reviewer_can_approve_pending_case(
    client,
    temp_env,
):
    payload = sample_link_eligible_payload(
        payment_id="pay_rev",
        order_id="order_rev",
    )

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_rev",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_rev"
    )

    assert case["policy_decision"] == "ALLOW"

    response = client.post(
        "/webhook-cases/order_rev/review",
        json={
            "decision": "approve",
            "approved_action": "CREATE_PAYMENT_LINK",
            "note": "Looks recoverable",
        },
        headers=auth_headers(
            temp_env["token"]
        ),
    )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["lifecycle_status"]
        == "APPROVED"
    )

    assert (
        body["approved_action"]
        == "CREATE_PAYMENT_LINK"
    )


def test_policy_blocked_case_cannot_be_approved(
    client,
    temp_env,
):
    payload = sample_failed_payload(
        payment_id="pay_block",
        order_id="order_block",
    )

    payload[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ][
        "error_reason"
    ] = "unknown"

    payload[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ][
        "amount"
    ] = 5000

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_block",
    )

    response = client.post(
        "/webhook-cases/order_block/review",
        json={
            "decision": "approve",
            "approved_action": "CREATE_PAYMENT_LINK",
        },
        headers=auth_headers(
            temp_env["token"]
        ),
    )

    assert response.status_code == 409


def test_execute_without_approval_fails(
    client,
    temp_env,
):
    payload = sample_link_eligible_payload(
        payment_id="pay_noexec",
        order_id="order_noexec",
    )

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_noexec",
    )

    response = client.post(
        "/webhook-cases/order_noexec/execute",
        headers=auth_headers(
            temp_env["token"]
        ),
    )

    assert response.status_code == 403


@patch(
    "backend.app.services.razorpay_execution_service.create_recovery_payment_link"
)
def test_payment_link_created_once_for_approved_case(
    mock_create,
    client,
    temp_env,
):
    mock_create.return_value = {
        "id": "plink_test_1",
        "short_url": "https://rzp.io/test",
        "reference_id": "RECOVERY_order_exec",
    }

    payload = sample_link_eligible_payload(
        payment_id="pay_exec",
        order_id="order_exec",
    )

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_exec",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_exec"
    )

    assert (
        case["policy_decision"]
        == "ALLOW"
    )

    client.post(
        "/webhook-cases/order_exec/review",
        json={
            "decision": "approve",
            "approved_action": "CREATE_PAYMENT_LINK",
        },
        headers=auth_headers(
            temp_env["token"]
        ),
    )

    first = client.post(
        "/webhook-cases/order_exec/execute",
        headers=auth_headers(
            temp_env["token"]
        ),
    )

    second = client.post(
        "/webhook-cases/order_exec/execute",
        headers=auth_headers(
            temp_env["token"]
        ),
    )

    assert first.status_code == 200
    assert second.status_code == 403

    assert (
        mock_create.call_count
        == 1
    )


@patch(
    "backend.app.services.razorpay_execution_service.create_recovery_payment_link"
)
def test_payment_captured_marks_recovery_case(
    mock_create,
    client,
    temp_env,
):
    mock_create.return_value = {
        "id": "plink_cap",
        "short_url": "https://rzp.io/cap",
        "reference_id": "RECOVERY_order_cap",
    }

    failed = sample_link_eligible_payload(
        payment_id="pay_cap_fail",
        order_id="order_cap",
    )

    post_webhook(
        client,
        failed,
        temp_env["webhook_secret"],
        "evt_cap_fail",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_cap"
    )

    assert (
        case["policy_decision"]
        == "ALLOW"
    )

    client.post(
        "/webhook-cases/order_cap/review",
        json={
            "decision": "approve",
            "approved_action": "CREATE_PAYMENT_LINK",
        },
        headers=auth_headers(
            temp_env["token"]
        ),
    )

    client.post(
        "/webhook-cases/order_cap/execute",
        headers=auth_headers(
            temp_env["token"]
        ),
    )

    captured = sample_captured_payload(
        payment_id="pay_cap_ok",
        order_id="order_created_for_payment_link",
        amount=250000,
    )

    captured["event"] = "payment_link.paid"

    captured["payload"]["payment_link"] = {
        "entity": {
            "reference_id": "RECOVERY_order_cap"
        }
    }

    response = post_webhook(
        client,
        captured,
        temp_env["webhook_secret"],
        "evt_cap_ok",
    )

    assert response.status_code == 200

    assert (
        response.json()["matched"]
        is True
    )

    updated = get_case(
        "order_cap"
    )

    assert (
        updated["lifecycle_status"]
        == "PAYMENT_CAPTURED"
    )


# ===========================================================================
# AI AUTO-APPROVAL TESTS
# ===========================================================================


@patch(
    "backend.app.services.razorpay_execution_service.create_recovery_payment_link"
)
@patch(
    "webhook_recovery.recommend_with_fallback"
)
def test_low_risk_ai_case_is_auto_approved_and_executed(
    mock_ai,
    mock_create,
    client,
    temp_env,
    monkeypatch,
):
    """
    With automatic recovery explicitly enabled, a low-value, first-attempt,
    transient failure with high-confidence
    AI CREATE_PAYMENT_LINK recommendation should automatically create
    a payment link without human review.
    """

    monkeypatch.setenv("ENABLE_AUTO_RECOVERY", "true")

    mock_ai.return_value = {
        "action": "CREATE_PAYMENT_LINK",
        "reason": (
            "Temporary bank timeout; creating a payment link "
            "is a safe recovery strategy."
        ),
        "confidence": 0.95,
        "risk_flags": [],
        "source": "ai",
    }

    mock_create.return_value = {
        "id": "plink_ai_auto",
        "short_url": "https://rzp.io/ai-auto",
        "reference_id": "RECOVERY_order_ai_auto",
    }

    payload = sample_failed_payload(
        payment_id="pay_ai_auto",
        order_id="order_ai_auto",
    )

    entity = payload[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ]

    entity["amount"] = 50000
    entity["error_reason"] = "bank_timeout"
    entity["error_code"] = "BANK_ERROR"

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_ai_auto",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_ai_auto"
    )

    assert (
        case["lifecycle_status"]
        == "LINK_CREATED"
    )

    assert (
        case["review_status"]
        == "APPROVE"
    )

    assert (
        case["recommended_action"]
        == "CREATE_PAYMENT_LINK"
    )

    assert (
        case["recovery_link_status"]
        == "CREATED"
    )

    assert (
        case["recovery_link_id"]
        == "plink_ai_auto"
    )

    assert (
        mock_create.call_count
        == 1
    )


@patch(
    "backend.app.services.razorpay_execution_service.create_recovery_payment_link"
)
@patch(
    "webhook_recovery.recommend_with_fallback"
)
def test_ai_auto_approval_rejects_high_amount(
    mock_ai,
    mock_create,
    client,
    temp_env,
):
    """
    Even with high AI confidence, amounts above the AI auto-approval
    limit must remain pending human review.
    """

    mock_ai.return_value = {
        "action": "CREATE_PAYMENT_LINK",
        "reason": "Recovery opportunity detected.",
        "confidence": 0.99,
        "risk_flags": [],
        "source": "ai",
    }

    payload = sample_failed_payload(
        payment_id="pay_ai_high",
        order_id="order_ai_high",
    )

    entity = payload[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ]

    entity["amount"] = 150000
    entity["error_reason"] = "bank_timeout"

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_ai_high",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_ai_high"
    )

    assert (
        case["lifecycle_status"]
        == "PENDING_REVIEW"
    )

    assert (
        case["recovery_link_status"]
        == "NOT_REQUESTED"
    )

    assert (
        mock_create.call_count
        == 0
    )


@patch(
    "backend.app.services.razorpay_execution_service.create_recovery_payment_link"
)
@patch(
    "webhook_recovery.recommend_with_fallback"
)
def test_ai_auto_approval_rejects_low_confidence(
    mock_ai,
    mock_create,
    client,
    temp_env,
):
    """
    Confidence below 0.90 must not result in automatic execution.
    """

    mock_ai.return_value = {
        "action": "CREATE_PAYMENT_LINK",
        "reason": "Possible recovery opportunity.",
        "confidence": 0.80,
        "risk_flags": [],
        "source": "ai",
    }

    payload = sample_failed_payload(
        payment_id="pay_ai_low_conf",
        order_id="order_ai_low_conf",
    )

    entity = payload[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ]

    entity["amount"] = 50000
    entity["error_reason"] = "bank_timeout"

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_ai_low_conf",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_ai_low_conf"
    )

    assert (
        case["lifecycle_status"]
        == "PENDING_REVIEW"
    )

    assert (
        case["recovery_link_status"]
        == "NOT_REQUESTED"
    )

    assert (
        mock_create.call_count
        == 0
    )


@patch(
    "backend.app.services.razorpay_execution_service.create_recovery_payment_link"
)
@patch(
    "webhook_recovery.recommend_with_fallback"
)
def test_ai_auto_approval_rejects_risk_flags(
    mock_ai,
    mock_create,
    client,
    temp_env,
):
    """
    Any AI risk flag forces human review.
    """

    mock_ai.return_value = {
        "action": "CREATE_PAYMENT_LINK",
        "reason": "Potential recovery opportunity.",
        "confidence": 0.97,
        "risk_flags": [
            "suspicious_activity",
        ],
        "source": "ai",
    }

    payload = sample_failed_payload(
        payment_id="pay_ai_risk",
        order_id="order_ai_risk",
    )

    entity = payload[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ]

    entity["amount"] = 50000
    entity["error_reason"] = "bank_timeout"

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_ai_risk",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_ai_risk"
    )

    assert (
        case["lifecycle_status"]
        == "PENDING_REVIEW"
    )

    assert (
        case["recovery_link_status"]
        == "NOT_REQUESTED"
    )

    assert (
        mock_create.call_count
        == 0
    )


@patch(
    "backend.app.services.razorpay_execution_service.create_recovery_payment_link"
)
@patch(
    "webhook_recovery.recommend_with_fallback"
)
def test_ai_auto_approval_rejects_non_transient_failure(
    mock_ai,
    mock_create,
    client,
    temp_env,
):
    """
    Generic/card/payment failures are not automatically recovered
    by this conservative AI gate.
    """

    mock_ai.return_value = {
        "action": "CREATE_PAYMENT_LINK",
        "reason": "Payment recovery opportunity.",
        "confidence": 0.98,
        "risk_flags": [],
        "source": "ai",
    }

    payload = sample_failed_payload(
        payment_id="pay_ai_generic",
        order_id="order_ai_generic",
    )

    entity = payload[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ]

    entity["amount"] = 50000
    entity["error_code"] = "BAD_REQUEST_ERROR"
    entity["error_description"] = "Payment failed"
    entity["error_reason"] = None

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_ai_generic",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_ai_generic"
    )

    assert (
        case["lifecycle_status"]
        == "PENDING_REVIEW"
    )

    assert (
        case["recovery_link_status"]
        == "NOT_REQUESTED"
    )

    assert (
        mock_create.call_count
        == 0
    )


@patch(
    "backend.app.services.razorpay_execution_service.create_recovery_payment_link"
)
@patch(
    "webhook_recovery.recommend_with_fallback"
)
def test_second_attempt_requires_human_review(
    mock_ai,
    mock_create,
    client,
    temp_env,
):
    """
    AI automatic approval is only allowed on the first recovery attempt.
    """

    mock_ai.return_value = {
        "action": "CREATE_PAYMENT_LINK",
        "reason": "Temporary failure recovery.",
        "confidence": 0.99,
        "risk_flags": [],
        "source": "ai",
    }

    # --------------------------------------------------------------
    # First failure
    # --------------------------------------------------------------

    first = sample_failed_payload(
        payment_id="pay_second_1",
        order_id="order_second",
    )

    entity = first[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ]

    entity["amount"] = 50000
    entity["error_reason"] = "bank_timeout"

    post_webhook(
        client,
        first,
        temp_env["webhook_secret"],
        "evt_second_1",
    )

    # --------------------------------------------------------------
    # Second failure for same order.
    # --------------------------------------------------------------

    second = sample_failed_payload(
        payment_id="pay_second_2",
        order_id="order_second",
    )

    entity = second[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ]

    entity["amount"] = 50000
    entity["error_reason"] = "bank_timeout"

    post_webhook(
        client,
        second,
        temp_env["webhook_secret"],
        "evt_second_2",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_second"
    )

    # The second attempt must not trigger another link.
    assert (
        mock_create.call_count
        <= 1
    )

    assert (
        case["lifecycle_status"]
        == "PENDING_REVIEW"
    )


@patch(
    "webhook_recovery.recommend_with_fallback"
)
def test_ai_auto_approval_requires_ai_source(
    mock_ai,
    client,
    temp_env,
):
    """
    Rule-based fallback recommendations must never be treated
    as AI auto-approved recommendations.
    """

    mock_ai.return_value = {
        "action": "CREATE_PAYMENT_LINK",
        "reason": "Fallback recommendation.",
        "confidence": 0.99,
        "risk_flags": [],
        "source": "rule_based_fallback",
    }

    payload = sample_failed_payload(
        payment_id="pay_fallback",
        order_id="order_fallback",
    )

    entity = payload[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ]

    entity["amount"] = 50000
    entity["error_reason"] = "bank_timeout"

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_fallback",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_fallback"
    )

    assert (
        case["lifecycle_status"]
        == "PENDING_REVIEW"
    )


@patch(
    "webhook_recovery.recommend_with_fallback"
)
def test_ai_auto_approval_rejects_human_review_action(
    mock_ai,
    client,
    temp_env,
):
    """
    HUMAN_REVIEW recommendations must remain human-review cases.
    """

    mock_ai.return_value = {
        "action": "HUMAN_REVIEW",
        "reason": "Needs human review.",
        "confidence": 0.99,
        "risk_flags": [],
        "source": "ai",
    }

    payload = sample_failed_payload(
        payment_id="pay_human_review",
        order_id="order_human_review",
    )

    entity = payload[
        "payload"
    ][
        "payment"
    ][
        "entity"
    ]

    entity["amount"] = 50000
    entity["error_reason"] = "bank_timeout"

    post_webhook(
        client,
        payload,
        temp_env["webhook_secret"],
        "evt_human_review",
    )

    from webhook_recovery import get_case

    case = get_case(
        "order_human_review"
    )

    assert (
        case["lifecycle_status"]
        == "PENDING_REVIEW"
    )
