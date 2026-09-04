"""Razorpay webhook and live recovery case routes."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal

from backend.app.auth import require_review_token
from create_payment_link import (
    create_test_payment_link,
    fetch_test_payment,
    fetch_test_payment_link,
)
from webhook_recovery import (
    execute_webhook_case,
    get_case,
    list_recovery_cases,
    make_event_id,
    process_captured_payment,
    process_failed_payment,
    record_review,
)

load_dotenv()

router = APIRouter(tags=["Razorpay Webhooks"])


class ReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]

    approved_action: Literal[
        "CREATE_PAYMENT_LINK"
    ] | None = None

    note: str | None = Field(
        default=None,
        max_length=500,
    )


class SimulationRequest(BaseModel):
    amount: float = Field(gt=0, le=100_000)
    failure_reason: Literal[
        "payment_failed", "network_error", "bank_timeout", "card_declined",
        "authentication_failed", "insufficient_funds", "upi_failure",
    ]
    previous_recovery_attempts: int = Field(default=0, ge=0, le=3)


class NormalPaymentRequest(BaseModel):
    amount: float = Field(gt=0, le=100_000)
    customer_name: str = Field(min_length=1, max_length=100)
    customer_email: str = Field(min_length=3, max_length=254)
    customer_contact: str = Field(min_length=8, max_length=20)


@router.get("/webhook-cases")
def webhook_cases(request: Request):
    require_review_token(request)

    cases = list_recovery_cases()

    return {
        "count": len(cases),
        "source": "razorpay_webhook",
        "cases": cases,
    }


@router.post("/test/simulate-failure")
def simulate_failed_payment(simulation: SimulationRequest, request: Request):
    """Create a clearly marked developer simulation via the normal pipeline."""
    require_review_token(request)
    if os.getenv("ENABLE_DEVELOPER_SIMULATION", "false").strip().lower() != "true":
        raise HTTPException(status_code=403, detail="Developer simulation is disabled. Set ENABLE_DEVELOPER_SIMULATION=true in the backend .env.")

    suffix = uuid.uuid4().hex[:12]
    payment = {
        "id": f"pay_sim_{suffix}",
        "order_id": f"order_sim_{suffix}",
        "amount": int(round(simulation.amount * 100)),
        "method": "upi",
        "contact": os.getenv("DEFAULT_RECOVERY_CONTACT") or "8610169138",
        "email": os.getenv("DEFAULT_RECOVERY_EMAIL") or "demo@example.com",
        "error_reason": simulation.failure_reason,
        "error_code": "BAD_REQUEST_ERROR" if simulation.failure_reason == "payment_failed" else None,
        "error_description": "Payment failed" if simulation.failure_reason == "payment_failed" else None,
        "error_source": "developer_simulation",
    }
    result = process_failed_payment(
        f"simulation:{suffix}", payment, source="simulation",
        previous_recovery_attempts_override=simulation.previous_recovery_attempts,
    )
    return {"simulated": True, "source": "simulation", **result}


@router.post("/payments/normal-link")
def create_normal_payment_link(payment: NormalPaymentRequest, request: Request):
    """Create an initial Razorpay Test Mode link; this is not recovery execution."""
    require_review_token(request)
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    if not key_id.startswith("rzp_test_"):
        raise HTTPException(status_code=403, detail="Only Razorpay Test Mode credentials are allowed.")
    try:
        transaction_id, link = create_test_payment_link(
            amount=payment.amount,
            customer_name=payment.customer_name,
            customer_email=payment.customer_email,
            customer_contact=payment.customer_contact,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Razorpay Test Mode payment-link creation failed.") from exc
    return {
        "created": True,
        "payment_type": "initial_normal_payment",
        "test_mode": True,
        "transaction_id": transaction_id,
        "payment_link_id": link.get("id"),
        "payment_link_url": link.get("short_url"),
        "reference_id": link.get("reference_id", transaction_id),
        "notify_customer": False,
    }


@router.get("/webhook-cases/{case_id}/payment-link")
def get_recovery_payment_link(case_id: str, request: Request):
    """Return the Test Mode URL for an already-created recovery link."""
    require_review_token(request)
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Recovery case not found.")
    link_id = case["recovery_link_id"]
    if not link_id:
        raise HTTPException(status_code=409, detail="A recovery payment link has not been created for this case.")
    try:
        link = fetch_test_payment_link(link_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to retrieve the Razorpay Test Mode payment link.") from exc
    return {
        "case_id": case_id,
        "payment_link_id": link_id,
        "payment_link_url": link.get("short_url"),
        "status": link.get("status"),
        "test_mode": True,
    }


@router.post("/webhook-cases/{case_id}/sync-payment")
def sync_recovery_payment(case_id: str, request: Request):
    """Reconcile an already-created Test Mode link if its webhook was missed."""
    require_review_token(request)
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Recovery case not found.")
    if not case["recovery_link_id"]:
        raise HTTPException(status_code=409, detail="A recovery payment link has not been created for this case.")
    try:
        link = fetch_test_payment_link(case["recovery_link_id"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to retrieve the Razorpay Test Mode payment link.") from exc
    payment_id = link.get("payment_id")
    if not payment_id:
        captured_payments = [
            item for item in (link.get("payments") or [])
            if item.get("status") == "captured" and item.get("payment_id")
        ]
        if captured_payments:
            payment_id = captured_payments[-1]["payment_id"]
    if link.get("status") != "paid" or not payment_id:
        return {"synced": False, "case_id": case_id, "payment_link_status": link.get("status", "unknown"), "detail": "Recovery payment has not been captured by Razorpay yet."}
    try:
        payment = fetch_test_payment(payment_id)
        result = process_captured_payment(
            f"reconciliation:{case['recovery_link_id']}:{payment_id}",
            payment,
            recovery_reference_id=link.get("reference_id"),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to reconcile the captured Razorpay payment.") from exc
    return {"synced": True, "source": "razorpay_reconciliation", "payment_link_status": "paid", **result}


@router.get("/recovery-cases/live")
def live_recovery_cases_alias(request: Request):
    return webhook_cases(request)


@router.post("/webhook-cases/{case_id}/review")
def review_webhook_case(
    case_id: str,
    review: ReviewRequest,
    request: Request,
):
    require_review_token(request)

    try:
        result = record_review(
            case_id,
            review.decision,
            review.note,
            review.approved_action,
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {
        "status": "review_recorded",
        **result,
    }


@router.post("/recovery-cases/{case_id}/review")
def review_live_case_alias(
    case_id: str,
    review: ReviewRequest,
    request: Request,
):
    return review_webhook_case(
        case_id,
        review,
        request,
    )


@router.post("/webhook-cases/{case_id}/execute")
def execute_webhook_case_endpoint(
    case_id: str,
    request: Request,
):
    """Create a Test Mode payment link for an approved case."""

    require_review_token(request)

    try:
        result = execute_webhook_case(
            case_id
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    if not result.get("executed"):
        raise HTTPException(
            status_code=403,
            detail=result.get(
                "reason",
                "Execution blocked.",
            ),
        )

    safe = {
        key: result[key]
        for key in (
            "executed",
            "case_id",
            "payment_link_id",
            "reference_id",
            "lifecycle_status",
            "audit",
            "note",
            "payment_link_url",
        )
        if key in result
    }

    return safe


@router.post("/webhook/razorpay")
async def razorpay_webhook(
    request: Request,
):
    webhook_secret = os.getenv(
        "WEBHOOK_SECRET"
    )

    if not webhook_secret:
        raise HTTPException(
            status_code=500,
            detail="Webhook verification is not configured.",
        )

    signature = request.headers.get(
        "X-Razorpay-Signature"
    )

    if not signature:
        raise HTTPException(
            status_code=400,
            detail="Missing webhook signature.",
        )

    raw_body = await request.body()

    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        signature,
        expected_signature,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook signature.",
        )

    try:
        payload = json.loads(raw_body)

    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload.",
        ) from exc

    event = payload.get("event")

    payment = (
        payload
        .get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )

    if event == "payment.failed":
        print(
            "RAZORPAY FAILURE DEBUG:",
            {
                "payment_id": payment.get("id"),
                "amount": payment.get("amount"),
                "order_id": payment.get("order_id"),
                "method": payment.get("method"),
                "error_code": payment.get("error_code"),
                "error_description": payment.get(
                    "error_description"
                ),
                "error_reason": payment.get(
                    "error_reason"
                ),
                "error_source": payment.get(
                    "error_source"
                ),
                "error_step": payment.get(
                    "error_step"
                ),
            },
        )

    payment_link = (
        payload
        .get("payload", {})
        .get("payment_link", {})
        .get("entity", {})
    )

    payment_id = payment.get("id")

    event_id = make_event_id(
        request.headers.get(
            "X-Razorpay-Event-Id"
        ),
        str(event),
        payment_id,
        raw_body,
    )

    if event == "payment.failed":

        try:
            result = process_failed_payment(
                event_id,
                payment,
            )

        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

        if result["duplicate"]:
            return {
                "status": "duplicate",
                "case_id": result["case_id"],
            }

        return {
            "status": "received",
            "case_id": result["case_id"],
        }

    if event in {
        "payment.captured",
        "payment_link.paid",
    }:

        try:
            result = process_captured_payment(
                event_id,
                payment,
                recovery_reference_id=(
                    payment_link.get(
                        "reference_id"
                    )
                    or payment.get(
                        "notes",
                        {},
                    ).get(
                        "reference_id"
                    )
                ),
            )

        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

        if result["duplicate"]:
            return {
                "status": "duplicate",
                "case_id": result["case_id"],
            }

        return {
            "status": "received",
            "case_id": result["case_id"],
            "matched": result.get(
                "matched",
                False,
            ),
        }

    return {
        "status": "ignored",
        "event": event,
    }
