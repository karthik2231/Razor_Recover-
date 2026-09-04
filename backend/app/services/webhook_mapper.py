"""Map Razorpay webhook payment payloads to recovery transaction records."""

from __future__ import annotations


def failure_reason(payment: dict) -> str:
    error_reason = str(payment.get("error_reason") or "").strip().lower()
    error_code = str(payment.get("error_code") or "").strip().lower()
    error_description = str(
        payment.get("error_description") or ""
    ).strip().lower()

    aliases = {
        "bank_timeout": "bank_timeout",
        "insufficient_fund": "insufficient_funds",
        "insufficient_funds": "insufficient_funds",
        "payment_timed_out": "bank_timeout",
        "gateway_technical_error": "network_error",
        "network_error": "network_error",
        "payment_failed": "payment_failed",
        "authentication_failed": "authentication_failed",
        "card_declined": "card_declined",
        "upi_failure": "upi_failure",
    }

    if error_reason in aliases:
        return aliases[error_reason]

    if error_code in aliases:
        return aliases[error_code]

    # Razorpay Test Mode generic failure.
    if error_code == "bad_request_error":
        return "payment_failed"

    if error_description == "payment failed":
        return "payment_failed"

    return "unknown"


def payment_method(payment: dict) -> str:
    method = str(payment.get("method") or "unknown").strip().lower()

    supported_methods = {
        "upi",
        "card",
        "netbanking",
        "wallet",
        "paylater",
        "emi",
        "bank_transfer",
    }

    return method if method in supported_methods else "unknown"


def payment_to_transaction(
    payment: dict,
    *,
    case_id: str,
    previous_recovery_attempts: int = 0,
) -> dict:
    try:
        amount_paise = int(payment.get("amount", 0) or 0)
    except (TypeError, ValueError):
        amount_paise = 0

    return {
        "transaction_id": case_id,
        "customer_id": (
            payment.get("email")
            or payment.get("contact")
            or case_id
        ),
        "amount": amount_paise / 100,
        "payment_status": "failed",
        "failure_reason": failure_reason(payment),
        "payment_method": payment_method(payment),

        "successful_payments": 0,
        "previous_recovery_attempts": previous_recovery_attempts,

        "razorpay_payment_id": payment.get("id"),
        "razorpay_order_id": payment.get("order_id"),

        "razorpay_error_code": payment.get("error_code"),
        "razorpay_error_description": payment.get("error_description"),
        "razorpay_error_reason": payment.get("error_reason"),
        "razorpay_error_source": payment.get("error_source"),
        "razorpay_error_step": payment.get("error_step"),

        "source": "webhook",
    }
