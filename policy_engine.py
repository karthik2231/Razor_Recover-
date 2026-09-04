"""
DEPRECATED — do not import this module in new code.

The canonical recovery policy lives in::

    backend.app.services.policy_service

This module exists only so that any remaining external scripts that were
written before the policy was moved into the backend package continue to
work. All production code paths — webhook handler, routes, tests — must
import directly from ``backend.app.services.policy_service``.
"""

import warnings

warnings.warn(
    "policy_engine is deprecated. "
    "Import from backend.app.services.policy_service instead.",
    DeprecationWarning,
    stacklevel=2,
)

from backend.app.services.policy_service import (  # noqa: E402, F401
    HIGH_VALUE_REVIEW_RUPEES,
    MAX_RECOVERY_ATTEMPTS,
    MIN_CONFIDENCE,
    check_policy,
    normalize_action,
)

__all__ = [
    "HIGH_VALUE_REVIEW_RUPEES",
    "MAX_RECOVERY_ATTEMPTS",
    "MIN_CONFIDENCE",
    "check_policy",
    "normalize_action",
]
