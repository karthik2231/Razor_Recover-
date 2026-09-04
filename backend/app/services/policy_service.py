"""Deterministic policy guardrails.

AI recommends; policy decides.

The policy engine is the final authority for automatic recovery.
Human approval can authorize a REVIEW case, but AI can never override
an explicit human rejection.
"""

from __future__ import annotations

import os

from backend.app.constants import (
    AI_AUTO_APPROVAL_FAILURE_REASONS,
    AI_AUTO_APPROVAL_LIMIT_RUPEES,
    AI_AUTO_APPROVAL_MIN_CONFIDENCE,
    EXECUTABLE_ACTIONS,
    LEGACY_ACTION_MAP,
    RECOVERY_ACTIONS,
)

# ---------------------------------------------------------------------------
# Global policy limits
# ---------------------------------------------------------------------------

MAX_RECOVERY_ATTEMPTS = 3

# Transactions above this amount are completely blocked from recovery.
# Business rule: any payment above INR 25,000 is not eligible for recovery.
HIGH_VALUE_REVIEW_RUPEES = 25_000

# Minimum confidence required for the general policy.
MIN_CONFIDENCE = 0.70

# ---------------------------------------------------------------------------
# AI automatic-approval limits
# ---------------------------------------------------------------------------

def _execution_limit_rupees() -> float:
    """Return the normal execution limit from the environment."""

    return float(
        os.getenv(
            "EXECUTION_LIMIT_RUPEES",
            "5000",
        )
    )


def normalize_action(action: str) -> str:
    """Normalize an AI/rule recommendation to the current vocabulary."""

    
    action = str(action or "").strip().upper()

    return LEGACY_ACTION_MAP.get(
        action,
        action,
    )


def check_policy(
    transaction: dict,
    ai_decision: dict,
) -> dict:
    """
    Apply deterministic recovery guardrails.

    Possible decisions:

        ALLOW  -> safe for automatic execution
        REVIEW -> human approval required
        DENY   -> recovery is blocked

    This function never executes anything.
    """

    action = normalize_action(
        # pyrefly: ignore [bad-argument-type]
        ai_decision.get(
            "recommended_action",
            ai_decision.get(
                "action",
                "",
            ),
        )
    )

    # ------------------------------------------------------------------
    # 1. Payment must still be failed
    # ------------------------------------------------------------------

    if transaction.get("payment_status") != "failed":
        return _deny(
            "Payment is no longer failed."
        )

    # Webhook payloads without a recognized failure reason are not safe to
    # recover. Preserve the original payment for investigation instead of
    # allowing a reviewer or an automated path to create a new charge.
    if str(transaction.get("failure_reason", "")).strip().lower() == "unknown":
        return _deny(
            "Payment failure reason is unknown and cannot be recovered safely."
        )

    # ------------------------------------------------------------------
    # 2. Prevent excessive recovery attempts
    # ------------------------------------------------------------------

    previous_attempts = int(
        transaction.get(
            "previous_recovery_attempts",
            0,
        )
        or 0
    )

    if previous_attempts >= MAX_RECOVERY_ATTEMPTS:
        return _deny(
            "Maximum recovery attempts reached."
        )

    # ------------------------------------------------------------------
    # 3. Fraud risk
    # ------------------------------------------------------------------

    risk_flags = [str(f).lower() for f in ai_decision.get("risk_flags", [])]
    if (
        str(
            ai_decision.get(
                "failure_category",
                "",
            )
        ).upper()
        == "FRAUD_RISK"
        or "fraud_risk" in risk_flags
        or "suspicious" in risk_flags
    ):
        return _deny(
            "Fraud risk detected; transaction is blocked from recovery."
        )

    # ------------------------------------------------------------------
    # 4. Explicit human review recommendation
    # ------------------------------------------------------------------

    if action == "HUMAN_REVIEW":
        return _review(
            "AI recommends human review before recovery."
        )

    # ------------------------------------------------------------------
    # 5. AI confidence
    # ------------------------------------------------------------------

    try:
        confidence = float(
            ai_decision.get(
                "confidence",
                0,
            )
            or 0
        )
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < MIN_CONFIDENCE:
        return _review(
            "Recommendation confidence is below the minimum threshold."
        )

    # ------------------------------------------------------------------
    # 6. Validate action
    # ------------------------------------------------------------------

    if action not in RECOVERY_ACTIONS:
        return _deny(
            "Recommended action is not recognized."
        )

    # ------------------------------------------------------------------
    # 7. Non-executable actions
    # ------------------------------------------------------------------

    if action not in EXECUTABLE_ACTIONS:
        return _deny(
            "Recommended action is not permitted for automatic execution."
        )

    # ------------------------------------------------------------------
    # 8. Amount-based routing (Tiered: <=1000 auto, >1000 human review)
    # ------------------------------------------------------------------

    amount = float(
        transaction.get(
            "amount",
            0,
        )
        or 0
    )

    execution_limit = _execution_limit_rupees()

    if amount > execution_limit:
        return _review(
            f"Amount exceeds maximum recovery execution limit of "
            f"INR {execution_limit:.0f}; "
            "human approval is required."
        )

    # ------------------------------------------------------------------
    # 9. All normal policy checks passed
    # ------------------------------------------------------------------

    if amount > AI_AUTO_APPROVAL_LIMIT_RUPEES:
        return _allow(
            action=action,
            reason=(
                f"Transaction passed recovery eligibility checks. "
                f"Human authorization required (amount exceeds zero-touch auto limit of INR {AI_AUTO_APPROVAL_LIMIT_RUPEES:,.0f})."
            ),
        )

    return _allow(
        action=action,
        reason="Transaction passed all automatic recovery policies.",
    )


def can_auto_approve_ai(
    transaction: dict,
    recommendation: dict,
    policy: dict,
) -> tuple[bool, str]:
    """
    Determine whether an AI recommendation may be automatically approved.

    This is deliberately stricter than check_policy().

    Requirements:

    - recommendation source must be "ai"
    - policy decision must be ALLOW
    - action must be CREATE_PAYMENT_LINK
    - payment must still be failed
    - first recovery attempt only
    - amount must be <= ₹1,000
    - failure must be a known transient failure
    - confidence must be >= 0.90
    - risk_flags must be empty

    This function never executes anything.
    """

    # ------------------------------------------------------------------
    # 1. Only genuine AI recommendations may use AI auto-approval.
    # ------------------------------------------------------------------

    if recommendation.get("source") != "ai":
        return (
            False,
            "Automatic approval requires an AI recommendation.",
        )

    # ------------------------------------------------------------------
    # 2. Deterministic policy must already allow the recommendation.
    # ------------------------------------------------------------------

    if policy.get("decision") != "ALLOW":
        return (
            False,
            "Policy decision is not ALLOW.",
        )

    # ------------------------------------------------------------------
    # 3. Only CREATE_PAYMENT_LINK is eligible.
    # ------------------------------------------------------------------

    action = normalize_action(
        # pyrefly: ignore [bad-argument-type]
        recommendation.get(
            "recommended_action",
            recommendation.get(
                "action",
                "",
            ),
        )
    )

    if action != "CREATE_PAYMENT_LINK":
        return (
            False,
            "Only CREATE_PAYMENT_LINK can be automatically approved.",
        )

    # ------------------------------------------------------------------
    # 4. Payment must still be failed.
    # ------------------------------------------------------------------

    if transaction.get("payment_status") != "failed":
        return (
            False,
            "Payment is no longer failed.",
        )

    # ------------------------------------------------------------------
    # 5. First recovery attempt only.
    # ------------------------------------------------------------------

    previous_attempts = int(
        transaction.get(
            "previous_recovery_attempts",
            0,
        )
        or 0
    )

    if previous_attempts != 0:
        return (
            False,
            "AI automatic approval is only permitted on the first recovery attempt.",
        )

    # ------------------------------------------------------------------
    # 6. Conservative AI amount limit.
    # ------------------------------------------------------------------

    try:
        amount = float(
            transaction.get(
                "amount",
                0,
            )
            or 0
        )
    except (TypeError, ValueError):
        return (
            False,
            "Transaction amount is invalid.",
        )

    if amount > AI_AUTO_APPROVAL_LIMIT_RUPEES:
        return (
            False,
            "Amount exceeds the AI automatic approval limit.",
        )

    # ------------------------------------------------------------------
    # 7. Only transient failures are eligible.
    # ------------------------------------------------------------------

    failure_reason = str(
        transaction.get(
            "failure_reason",
            "",
        )
        or ""
    ).strip().lower()

    if failure_reason not in AI_AUTO_APPROVAL_FAILURE_REASONS:
        return (
            False,
            "Failure reason is not eligible for AI automatic approval.",
        )

    # ------------------------------------------------------------------
    # 8. AI confidence must be high enough.
    # ------------------------------------------------------------------

    try:
        confidence = float(
            recommendation.get(
                "confidence",
                0,
            )
            or 0
        )
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < AI_AUTO_APPROVAL_MIN_CONFIDENCE:
        return (
            False,
            "AI confidence is below the minimum automatic approval threshold.",
        )

    # ------------------------------------------------------------------
    # 9. Any risk flag forces human review.
    # ------------------------------------------------------------------

    risk_flags = recommendation.get(
        "risk_flags",
        [],
    )

    if risk_flags:
        return (
            False,
            "AI risk flags require human review.",
        )

    # ------------------------------------------------------------------
    # 10. Everything passed.
    # ------------------------------------------------------------------

    return (
        True,
        "AI recommendation passed all automatic approval guardrails.",
    )


def evaluate_policy(
    transaction: dict,
    recommendation: dict,
) -> dict:
    """
    Public policy interface used by the recovery pipeline.

    This wraps check_policy() and exposes the richer structure expected
    by the webhook/recovery services.
    """

    policy = check_policy(
        transaction,
        recommendation,
    )

    decision = policy["decision"]

    executable = decision == "ALLOW"

    final_action = normalize_action(
        # pyrefly: ignore [bad-argument-type]
        recommendation.get(
            "recommended_action",
            recommendation.get(
                "action",
                "",
            ),
        )
    )

    if decision == "ALLOW":
        final_status = "ALLOWED"
    elif decision == "REVIEW":
        final_status = "REVIEW"
    else:
        final_status = "BLOCKED"

    return {
        "policy": policy,
        "decision": decision,
        "reason": policy["reason"],
        "final_action": final_action,
        "final_reason": policy["reason"],
        "final_status": final_status,
        "executable": executable,
        "executed": False,
    }


def _allow(
    *,
    action: str,
    reason: str,
) -> dict:
    """Allow automatic execution."""

    return {
        "decision": "ALLOW",
        "reason": reason,
        "action": action,
    }


def _review(
    reason: str,
) -> dict:
    """Send the transaction to human review."""

    return {
        "decision": "REVIEW",
        "reason": reason,
    }


def _deny(
    reason: str,
) -> dict:
    """Block recovery."""

    return {
        "decision": "DENY",
        "reason": reason,
    }
