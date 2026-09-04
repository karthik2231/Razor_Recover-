"""End-to-end recovery analysis: score, recommend, apply policy. No execution."""

from __future__ import annotations

from backend.app.services.ai_decision_service import recommend_with_fallback
from backend.app.services.audit_service import (
    has_executed_recovery,
    log_batch_analysis,
    log_executed_recovery,
    log_recovery_analysis,
    log_simulated_recovery,
)
from backend.app.services.decision_service import decide_recovery_action
from backend.app.services.policy_service import evaluate_policy
from backend.app.services.razorpay_execution_service import (
    ExecutionError,
    execute_payment_link_recovery,
    validate_execution_request,
)
from backend.app.services.transaction_service import get_scored_failed_transactions


def _analyze_path(transaction: dict, recommendation: dict) -> dict:
    return {
        "recommendation": recommendation,
        "outcome": evaluate_policy(transaction, recommendation),
    }


def recover_transaction(transaction: dict, *, use_ai: bool = True) -> dict:
    """Run the full recovery pipeline for one scored failed transaction."""
    rule_recommendation = decide_recovery_action(transaction)
    result = {
        "transaction": transaction,
        "rule_based": _analyze_path(transaction, rule_recommendation),
    }

    if use_ai:
        ai_recommendation = recommend_with_fallback(transaction)
        result["ai"] = _analyze_path(transaction, ai_recommendation)
        result["authoritative"] = result["ai"]["outcome"]
    else:
        result["authoritative"] = result["rule_based"]["outcome"]

    result["note"] = (
        "Analysis only. Policy engine has final authority; "
        "no recovery action was executed."
    )
    result["audit"] = log_recovery_analysis(
        transaction,
        result,
        analysis_mode="ai" if use_ai else "rule_based",
    )
    return result


def simulate_recovery(transaction: dict, *, use_ai: bool = True) -> dict:
    """Simulate bounded recovery for an approved case. Does not call Razorpay."""
    analysis = recover_transaction(transaction, use_ai=use_ai)
    outcome = analysis["authoritative"]

    if not outcome.get("executable"):
        return {
            "simulated": False,
            "reason": outcome.get("final_reason"),
            "analysis": analysis,
        }

    audit = log_simulated_recovery(
        transaction,
        outcome,
        analysis_mode="ai" if use_ai else "rule_based",
    )

    return {
        "simulated": True,
        "transaction_id": transaction.get("transaction_id"),
        "amount_rupees": float(transaction.get("amount", 0) or 0),
        "final_action": outcome.get("final_action"),
        "recovery_status": "simulated_success",
        "audit": audit,
        "note": (
            "Simulated recovery only. No Razorpay payment link was created."
        ),
    }


def execute_recovery(
    transaction: dict,
    *,
    use_ai: bool = False,
    customer_contact: str | None = None,
    customer_email: str | None = None,
) -> dict:
    """Execute bounded Razorpay Test Mode recovery for a policy-approved case."""
    transaction_id = str(transaction.get("transaction_id"))
    analysis = recover_transaction(transaction, use_ai=use_ai)
    outcome = analysis["authoritative"]
    analysis_mode = "ai" if use_ai else "rule_based"

    try:
        validate_execution_request(
            transaction,
            outcome,
            already_executed=has_executed_recovery(transaction_id),
        )
        execution_result = execute_payment_link_recovery(
            transaction,
            customer_contact=customer_contact,
            customer_email=customer_email,
        )
    except ExecutionError as exc:
        return {
            "executed": False,
            "reason": str(exc),
            "analysis": analysis,
        }

    audit = log_executed_recovery(
        transaction,
        outcome,
        execution_result,
        analysis_mode=analysis_mode,
    )

    return {
        **execution_result,
        "analysis": analysis,
        "audit": audit,
        "note": (
            "Test Mode payment link created. Customer was not notified automatically."
        ),
    }


def batch_recover(*, use_ai: bool = False, limit: int | None = None) -> dict:
    """Analyze all failed transactions and return measurable batch results."""
    cases = get_scored_failed_transactions()
    if limit is not None:
        cases = cases[:limit]

    analyzed_cases = []
    approved_count = 0
    blocked_count = 0
    approved_amount = 0.0
    blocked_amount = 0.0

    for transaction in cases:
        rule_recommendation = decide_recovery_action(transaction)
        outcome = evaluate_policy(transaction, rule_recommendation)

        if use_ai:
            ai_recommendation = recommend_with_fallback(transaction)
            outcome = evaluate_policy(transaction, ai_recommendation)
            path = _analyze_path(transaction, ai_recommendation)
        else:
            path = _analyze_path(transaction, rule_recommendation)

        amount = float(transaction.get("amount", 0) or 0)
        if outcome["executable"]:
            approved_count += 1
            approved_amount += amount
        else:
            blocked_count += 1
            blocked_amount += amount

        analyzed_cases.append(
            {
                "transaction_id": transaction["transaction_id"],
                "amount": amount,
                "recovery_score": transaction.get("recovery_score"),
                "opportunity": transaction.get("opportunity"),
                "failure_reason": transaction.get("failure_reason"),
                "recommendation": path["recommendation"],
                "outcome": path["outcome"],
            }
        )

    summary = {
        "total_cases": len(analyzed_cases),
        "approved_for_execution": approved_count,
        "blocked_by_policy": blocked_count,
        "approved_amount_rupees": round(approved_amount, 2),
        "blocked_amount_rupees": round(blocked_amount, 2),
        "analysis_mode": "ai" if use_ai else "rule_based",
    }

    audit = log_batch_analysis(summary, analysis_mode=summary["analysis_mode"])

    return {
        "summary": summary,
        "cases": analyzed_cases,
        "audit": audit,
        "note": (
            "Batch analysis only. Policy engine has final authority; "
            "no recovery actions were executed."
        ),
    }
