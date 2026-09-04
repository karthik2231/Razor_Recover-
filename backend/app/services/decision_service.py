"""Rule-based recovery recommendations."""

from __future__ import annotations


def decide_recovery_action(transaction: dict) -> dict:
    """
    Return a conservative rule-based recovery recommendation.

    This is the fallback when AI is unavailable.

    The policy engine remains authoritative and decides whether the
    recommendation may actually be executed.
    """

    score = int(transaction.get("recovery_score", 0) or 0)
    opportunity = str(
        transaction.get("opportunity", "LOW")
    ).upper()

    failure_reason = str(
        transaction.get("failure_reason", "")
    ).lower()

    attempts = int(
        transaction.get("previous_recovery_attempts", 0) or 0
    )

    # Hard safety limit.
    if attempts >= 3:
        return {
            "action": "DO_NOT_CONTACT",
            "reason": "Maximum recovery attempts reached.",
            "confidence": 0.95,
            "risk_flags": ["max_attempts"],
            "source": "rule_based",
        }

    # Transient / generic failures are safe candidates for link recovery
    # on the first attempt.
    #
    # payment_failed is Razorpay's generic code for a transient failure
    # and is already classified as safe in AI_AUTO_APPROVAL_FAILURE_REASONS.
    # Confidence is set to 0.90 so this also passes the AI auto-approval
    # guardrail (AI_AUTO_APPROVAL_MIN_CONFIDENCE) when Gemini is unavailable.
    if failure_reason in {
        "bank_timeout",
        "network_error",
        "upi_failure",    # transient — same risk class as bank/network
        "payment_failed", # Razorpay generic transient; safe on first attempt
    } and attempts == 0:
        return {
            "action": "CREATE_PAYMENT_LINK",
            "reason": (
                "Transient payment failure detected on the first "
                "recovery attempt; recovery link is recommended."
            ),
            "confidence": 0.90,
            "risk_flags": [],
            "source": "rule_based",
        }

    # Payment method problems.
    if failure_reason in {
        "authentication_failed",
        "card_declined",
    } and attempts <= 1:
        return {
            "action": "REQUEST_PAYMENT_METHOD_CHANGE",
            "reason": (
                "Payment method issue may be resolved by requesting "
                "updated payment details."
            ),
            "confidence": 0.78,
            "risk_flags": [],
            "source": "rule_based",
        }

    # payment_failed on subsequent attempts (attempts > 0) needs human review
    # since the transient path above only fires on attempts == 0.
    if failure_reason == "payment_failed":
        return {
            "action": "HUMAN_REVIEW",
            "reason": (
                "Repeated generic payment failure; human review required "
                "before attempting further recovery."
            ),
            "confidence": 0.65,
            "risk_flags": ["repeated_payment_failed"],
            "source": "rule_based",
        }

    # High-value recovery opportunity.
    if opportunity == "HIGH" and attempts <= 1:
        return {
            "action": "CREATE_PAYMENT_LINK",
            "reason": (
                "High recovery opportunity with limited previous "
                "recovery attempts."
            ),
            "confidence": 0.88,
            "risk_flags": [],
            "source": "rule_based",
        }

    # Medium opportunity.
    if opportunity == "MEDIUM" and attempts <= 1:
        return {
            "action": "CREATE_PAYMENT_LINK",
            "reason": (
                "Moderate recovery opportunity; a payment link is "
                "suitable for recovery."
            ),
            "confidence": 0.75,
            "risk_flags": [],
            "source": "rule_based",
        }

    # Low score.
    if score < 40:
        return {
            "action": "HUMAN_REVIEW",
            "reason": (
                "Low recovery opportunity requires human review."
            ),
            "confidence": 0.70,
            "risk_flags": ["low_score"],
            "source": "rule_based",
        }

    return {
        "action": "HUMAN_REVIEW",
        "reason": (
            "Case does not match a safe automated recovery strategy."
        ),
        "confidence": 0.65,
        "risk_flags": ["unmatched_case"],
        "source": "rule_based",
    }