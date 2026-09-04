"""Policy and execution guardrail tests."""

from __future__ import annotations

import pytest

from backend.app.services.policy_service import (
    can_auto_approve_ai,
    check_policy,
    evaluate_policy,
)
from backend.app.services.razorpay_execution_service import (
    ExecutionError,
    validate_execution_request,
)


def test_policy_blocks_fraud_risk_transaction():
    transaction = {
        "transaction_id": "TXN_FRAUD",
        "amount": 500,
        "payment_status": "failed",
        "previous_recovery_attempts": 0,
    }

    ai_decision = {
        "failure_category": "FRAUD_RISK",
        "recommended_action": "CREATE_PAYMENT_LINK",
        "confidence": 0.92,
    }

    result = check_policy(
        transaction,
        ai_decision,
    )

    assert result["decision"] == "DENY"
    assert "Fraud" in result["reason"]


def test_policy_routes_high_value_to_human_review():
    transaction = {
        "transaction_id": "TXN_HIGH_REVIEW",
        "amount": 30_000,
        "payment_status": "failed",
        "failure_reason": "bank_timeout",
        "previous_recovery_attempts": 0,
    }

    ai_decision = {
        "failure_category": "TRANSIENT_TECHNICAL_ERROR",
        "recommended_action": "CREATE_PAYMENT_LINK",
        "confidence": 0.95,
    }

    result = check_policy(
        transaction,
        ai_decision,
    )

    assert result["decision"] == "REVIEW"


def test_policy_allows_normal_transaction():
    transaction = {
        "transaction_id": "TXN_ALLOW",
        "amount": 500,
        "payment_status": "failed",
        "failure_reason": "bank_timeout",
        "previous_recovery_attempts": 0,
    }

    ai_decision = {
        "failure_category": "TRANSIENT_TECHNICAL_ERROR",
        "recommended_action": "CREATE_PAYMENT_LINK",
        "confidence": 0.95,
    }

    result = check_policy(
        transaction,
        ai_decision,
    )

    assert result["decision"] == "ALLOW"
    assert result["action"] == "CREATE_PAYMENT_LINK"


def test_policy_reviews_low_confidence():
    transaction = {
        "transaction_id": "TXN_LOW_CONF",
        "amount": 500,
        "payment_status": "failed",
        "previous_recovery_attempts": 0,
    }

    ai_decision = {
        "recommended_action": "CREATE_PAYMENT_LINK",
        "confidence": 0.50,
    }

    result = check_policy(
        transaction,
        ai_decision,
    )

    assert result["decision"] == "REVIEW"


def test_policy_reviews_amount_above_execution_limit(
    monkeypatch,
):
    monkeypatch.setenv(
        "EXECUTION_LIMIT_RUPEES",
        "1000",
    )

    transaction = {
        "transaction_id": "TXN_LIMIT",
        "amount": 2500,
        "payment_status": "failed",
        "previous_recovery_attempts": 0,
    }

    ai_decision = {
        "recommended_action": "CREATE_PAYMENT_LINK",
        "confidence": 0.95,
    }

    result = check_policy(
        transaction,
        ai_decision,
    )

    assert result["decision"] == "REVIEW"


def test_execution_fails_for_live_mode_key(
    monkeypatch,
):
    monkeypatch.setenv(
        "RAZORPAY_KEY_ID",
        "rzp_live_bad",
    )

    monkeypatch.setenv(
        "RAZORPAY_KEY_SECRET",
        "secret",
    )

    transaction = {
        "transaction_id": "TXN1",
        "amount": 100,
        "payment_status": "failed",
    }

    outcome = {
        "executable": True,
        "final_action": "CREATE_PAYMENT_LINK",
        "final_reason": "ok",
    }

    with pytest.raises(
        ExecutionError,
        match="Test Mode",
    ):
        validate_execution_request(
            transaction,
            outcome,
            already_executed=False,
        )


def test_execution_fails_above_amount_limit(
    monkeypatch,
):
    monkeypatch.setenv(
        "RAZORPAY_KEY_ID",
        "rzp_test_fake",
    )

    monkeypatch.setenv(
        "RAZORPAY_KEY_SECRET",
        "secret",
    )

    monkeypatch.setenv(
        "EXECUTION_LIMIT_RUPEES",
        "1000",
    )

    transaction = {
        "transaction_id": "TXN2",
        "amount": 2500,
        "payment_status": "failed",
    }

    outcome = {
        "executable": True,
        "final_action": "CREATE_PAYMENT_LINK",
        "final_reason": "ok",
    }

    with pytest.raises(
        ExecutionError,
        match="exceeds the execution limit",
    ):
        validate_execution_request(
            transaction,
            outcome,
            already_executed=False,
        )


def test_execution_fails_when_policy_blocks():
    transaction = {
        "transaction_id": "TXN3",
        "amount": 100,
        "payment_status": "failed",
    }

    outcome = {
        "executable": False,
        "final_action": "HUMAN_REVIEW",
        "final_reason": "Blocked",
    }

    with pytest.raises(
        ExecutionError,
        match="Blocked",
    ):
        validate_execution_request(
            transaction,
            outcome,
            already_executed=False,
        )


def test_ai_malformed_output_falls_back_to_rules(
    monkeypatch,
):
    from backend.app.services.ai_decision_service import (
        AIDecisionError,
        recommend_with_fallback,
    )

    transaction = {
        "transaction_id": "TXN4",
        "amount": 2500,
        "payment_status": "failed",
        "failure_reason": "bank_timeout",
        "payment_method": "upi",
        "successful_payments": 10,
        "previous_recovery_attempts": 0,
        "recovery_score": 75,
        "opportunity": "HIGH",
    }

    def boom(_txn):
        raise AIDecisionError(
            "bad ai"
        )

    monkeypatch.setattr(
        "backend.app.services.ai_decision_service.recommend_recovery_action",
        boom,
    )

    result = recommend_with_fallback(
        transaction
    )

    assert result["source"] == "rule_based_fallback"
    assert result["ai_failure"] == "bad ai"
    assert "action" in result


def test_only_matched_captured_payments_count_in_metrics(
    temp_env,
    monkeypatch,
):
    import backend.app.services.audit_service as audit_service

    monkeypatch.setattr(
        audit_service,
        "AUDIT_FILE",
        temp_env["audit_path"],
    )

    audit_service.log_webhook_captured(
        case_id="matched_case",
        payment_id="pay1",
        amount_rupees=500.0,
        matched=True,
    )

    audit_service.log_webhook_captured(
        case_id="ignored_case",
        payment_id="pay2",
        amount_rupees=999.0,
        matched=False,
    )

    metrics = audit_service.get_recovery_metrics(
        {
            "total_revenue_at_risk": 1000,
            "failed_transaction_count": 1,
        },
        db_path=temp_env["db_path"],
    )

    assert metrics["recovered_amount_rupees"] == 500.0
    assert metrics["recovered_cases"] == 1


def test_human_review_action_is_not_executable():
    transaction = {
        "transaction_id": "TXN5",
        "amount": 500,
        "payment_status": "failed",
        "failure_reason": "unknown",
        "previous_recovery_attempts": 0,
    }

    recommendation = {
        "action": "HUMAN_REVIEW",
        "reason": "Needs review",
        "confidence": 0.70,
        "risk_flags": [],
    }

    outcome = evaluate_policy(
        transaction,
        recommendation,
    )

    assert outcome["executable"] is False
    assert outcome["decision"] == "DENY"
    assert outcome["final_status"] == "BLOCKED"


@pytest.mark.parametrize(
    ("amount", "failure_reason", "attempts", "risk_flags", "expected"),
    [
        (450, "payment_failed", 0, [], True),
        (999, "network_error", 0, [], True),
        (1000, "bank_timeout", 0, [], True),
        (1001, "payment_failed", 0, [], False),
        (500, "payment_failed", 1, [], False),
        (500, "card_declined", 0, [], False),
        (500, "payment_failed", 0, ["fraud_risk"], False),
        (5000, "payment_failed", 0, [], False),
    ],
)
def test_ai_auto_approval_criteria(
    amount,
    failure_reason,
    attempts,
    risk_flags,
    expected,
):
    transaction = {
        "transaction_id": "TXN_AUTO",
        "amount": amount,
        "payment_status": "failed",
        "failure_reason": failure_reason,
        "previous_recovery_attempts": attempts,
        # Deliberately low — auto-approval must not depend on score.
        "recovery_score": 35,
        "opportunity": "LOW",
    }
    recommendation = {
        "action": "CREATE_PAYMENT_LINK",
        "confidence": 0.95,
        "risk_flags": risk_flags,
        "source": "ai",
    }
    policy = evaluate_policy(transaction, recommendation)["policy"]

    approved, _ = can_auto_approve_ai(transaction, recommendation, policy)

    assert approved is expected


def test_ai_normalizes_only_an_exactly_auto_eligible_human_review():
    from backend.app.services.ai_decision_service import (
        _normalize_auto_eligible_recommendation,
    )

    recommendation = _normalize_auto_eligible_recommendation(
        {
            "payment_status": "failed",
            "amount": 450,
            "failure_reason": "payment_failed",
            "previous_recovery_attempts": 0,
            "recovery_score": 35,
        },
        {
            "action": "HUMAN_REVIEW",
            "confidence": 0.95,
            "risk_flags": [],
        },
    )

    assert recommendation["action"] == "CREATE_PAYMENT_LINK"
    assert recommendation["normalization"] == "auto_recovery_eligible_action"


if __name__ == "__main__":
    pytest.main([__file__])

