"""Bounded Razorpay Test Mode recovery execution. Policy must approve first."""

from __future__ import annotations

import os
from pathlib import Path 

from dotenv import load_dotenv

from create_payment_link import create_recovery_payment_link as _create_recovery_payment_link

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

EXECUTABLE_ACTIONS = frozenset({"CREATE_PAYMENT_LINK"})


def create_recovery_payment_link(**kwargs: object) -> dict:
    """Create a Test Mode recovery link through the Razorpay adapter.

    Keeping this named adapter gives callers and tests one stable execution
    seam while the underlying Razorpay helper remains replaceable.
    """

    try:
        return _create_recovery_payment_link(**kwargs)
    except Exception as exc:
        raise ExecutionError(
            "Razorpay Test Mode payment-link creation failed."
        ) from exc


def _execution_limit_rupees() -> float:
    return float(os.getenv("EXECUTION_LIMIT_RUPEES", "5000"))


class ExecutionError(Exception):
    """Raised when recovery cannot be executed safely."""


def _require_test_mode_credentials() -> None:
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")

    if not key_id or not key_secret:
        raise ExecutionError(
            "Razorpay credentials are not configured. "
            "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in the root .env file."
        )

    if not key_id.startswith("rzp_test_"):
        raise ExecutionError(
            "Only Razorpay Test Mode credentials (rzp_test_*) are allowed."
        )


def _customer_details(transaction: dict, *, contact: str | None, email: str | None) -> dict:
    customer_id = str(transaction.get("customer_id") or "customer")
    resolved_contact = contact or os.getenv("DEFAULT_RECOVERY_CONTACT")
    resolved_email = email or os.getenv(
        "DEFAULT_RECOVERY_EMAIL",
        f"{customer_id.lower()}@revenuerescue.test",
    )

    if not resolved_contact:
        raise ExecutionError(
            "A customer contact is required. Pass customer_contact or set "
            "DEFAULT_RECOVERY_CONTACT in .env."
        )

    return {
        "name": customer_id.replace("_", " "),
        "email": resolved_email,
        "contact": resolved_contact,
    }


def validate_execution_request(
    transaction: dict,
    outcome: dict,
    *,
    already_executed: bool,
) -> None:
    """Raise ExecutionError when a case must not call Razorpay."""
    if already_executed:
        raise ExecutionError(
            f"Recovery for {transaction.get('transaction_id')} was already executed."
        )

    if not outcome.get("executable"):
        raise ExecutionError(outcome.get("final_reason") or "Policy blocked execution.")

    final_action = outcome.get("final_action")
    if final_action not in EXECUTABLE_ACTIONS:
        raise ExecutionError(
            f"Action '{final_action}' cannot be executed via Razorpay payment links. "
            "Only CREATE_PAYMENT_LINK is supported."
        )

    amount = float(transaction.get("amount", 0) or 0)
    limit = _execution_limit_rupees()
    if amount > limit:
        raise ExecutionError(
            f"Amount INR {amount:.0f} exceeds the execution limit of INR {limit:.0f}."
        )

    _require_test_mode_credentials()


def execute_payment_link_recovery(
    transaction: dict,
    *,
    customer_contact: str | None = None,
    customer_email: str | None = None,
) -> dict:
    """Create one non-notifying Test Mode payment link for an approved case."""
    customer = _customer_details(
        transaction,
        contact=customer_contact,
        email=customer_email,
    )
    amount = float(transaction.get("amount", 0) or 0)
    transaction_id = str(transaction.get("transaction_id"))

    payment_link = create_recovery_payment_link(
        transaction_id=f"TEST_{transaction_id}",
        amount=amount,
        customer_name=customer["name"],
        customer_email=customer["email"],
        customer_contact=customer["contact"],
        notify_customer=False,
    )

    return {
        "executed": True,
        "execution_type": "razorpay_payment_link",
        "transaction_id": transaction_id,
        "amount_rupees": amount,
        "payment_link_id": payment_link.get("id"),
        "payment_link_url": payment_link.get("short_url"),
        "reference_id": payment_link.get("reference_id"),
        "test_mode": True,
        "notify_customer": False,
    }
