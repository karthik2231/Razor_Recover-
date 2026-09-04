"""Shared constants for RevenueRescue AI."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Recovery action vocabulary
# ---------------------------------------------------------------------------

RECOVERY_ACTIONS = frozenset(
    {
        "CREATE_PAYMENT_LINK",
        "RETRY_PAYMENT",
        "REQUEST_PAYMENT_METHOD_CHANGE",
        "SEND_REMINDER",
        "HUMAN_REVIEW",
        "DO_NOT_CONTACT",
    }
)


# Actions that may execute automatically through Razorpay.
EXECUTABLE_ACTIONS = frozenset(
    {
        "CREATE_PAYMENT_LINK",
    }
)


# ---------------------------------------------------------------------------
# Legacy action aliases
# ---------------------------------------------------------------------------

LEGACY_ACTION_MAP = {
    "ESCALATE": "HUMAN_REVIEW",
    "STOP": "DO_NOT_CONTACT",
}


# ---------------------------------------------------------------------------
# Case lifecycle statuses
# ---------------------------------------------------------------------------

LIFECYCLE_PENDING_REVIEW = "PENDING_REVIEW"
LIFECYCLE_APPROVED = "APPROVED"
LIFECYCLE_REJECTED = "REJECTED"
LIFECYCLE_LINK_CREATED = "LINK_CREATED"
LIFECYCLE_PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
LIFECYCLE_EXECUTION_FAILED = "EXECUTION_FAILED"
LIFECYCLE_POLICY_BLOCKED = "POLICY_BLOCKED"


# ---------------------------------------------------------------------------
# AI automatic approval guardrails
#
# These are deliberately conservative.
#
# AI does NOT get authority to override the policy engine.
# These values only determine whether an already-policy-approved
# CREATE_PAYMENT_LINK recommendation can skip human review.
# ---------------------------------------------------------------------------

AI_AUTO_APPROVAL_LIMIT_RUPEES = 1000.0

AI_AUTO_APPROVAL_MIN_CONFIDENCE = 0.90

AI_AUTO_APPROVAL_MAX_ATTEMPTS = 0

AI_AUTO_APPROVAL_FAILURE_REASONS = frozenset(
    {
        "bank_timeout",
        "network_error",
        "payment_failed",
        "upi_failure",   # transient — same risk profile as bank_timeout
    }
)
