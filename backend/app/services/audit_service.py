"""Append-only audit trail for recovery analysis and outcomes."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
AUDIT_FILE = BASE_DIR / "data" / "audit_log.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_entry(entry: dict) -> dict:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {"audit_id": str(uuid.uuid4()), "timestamp": _now_iso(), **entry}

    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    return record


def _sanitize_entry(entry: dict) -> dict:
    sanitized = dict(entry)
    sanitized.pop("payment_link_url", None)
    return sanitized


def log_recovery_analysis(
    transaction: dict,
    analysis_result: dict,
    *,
    analysis_mode: str,
    source: str = "csv",
) -> dict:
    authoritative = analysis_result.get("authoritative", {})
    recommendation = (
        analysis_result.get("ai", {}).get("recommendation")
        if analysis_mode == "ai"
        else analysis_result.get("rule_based", {}).get("recommendation")
    )

    return _append_entry(
        {
            "event_type": "RECOVERY_ANALYSIS",
            "source": source,
            "analysis_mode": analysis_mode,
            "transaction_id": transaction.get("transaction_id"),
            "amount_rupees": float(transaction.get("amount", 0) or 0),
            "failure_reason": transaction.get("failure_reason"),
            "recovery_score": transaction.get("recovery_score"),
            "recommendation": {
                "action": recommendation.get("action"),
                "confidence": recommendation.get("confidence"),
                "reason": recommendation.get("reason"),
                "risk_flags": recommendation.get("risk_flags", []),
                "source": recommendation.get("source"),
                "ai_failure": recommendation.get("ai_failure"),
            },
            "ai_auto_approval": analysis_result.get("ai_auto_approval"),
            "policy_decision": authoritative.get("policy", {}).get("decision"),
            "final_action": authoritative.get("final_action"),
            "final_status": authoritative.get("final_status"),
            "executable": authoritative.get("executable", False),
            "executed": False,
        }
    )


def log_batch_analysis(summary: dict, *, analysis_mode: str) -> dict:
    return _append_entry(
        {
            "event_type": "BATCH_ANALYSIS",
            "analysis_mode": analysis_mode,
            "summary": summary,
            "executed": False,
        }
    )


def log_simulated_recovery(
    transaction: dict,
    outcome: dict,
    *,
    analysis_mode: str,
) -> dict:
    return _append_entry(
        {
            "event_type": "RECOVERY_SIMULATED",
            "analysis_mode": analysis_mode,
            "transaction_id": transaction.get("transaction_id"),
            "amount_rupees": float(transaction.get("amount", 0) or 0),
            "final_action": outcome.get("final_action"),
            "policy_decision": outcome.get("policy", {}).get("decision"),
            "executable": True,
            "executed": True,
            "recovery_status": "simulated_success",
        }
    )


def log_executed_recovery(
    transaction: dict,
    outcome: dict,
    execution_result: dict,
    *,
    analysis_mode: str,
    source: str = "csv",
    include_url: bool = False,
) -> dict:
    entry = {
        "event_type": "RECOVERY_EXECUTED",
        "source": source,
        "analysis_mode": analysis_mode,
        "transaction_id": transaction.get("transaction_id"),
        "amount_rupees": float(transaction.get("amount", 0) or 0),
        "final_action": outcome.get("final_action"),
        "policy_decision": outcome.get("policy", {}).get("decision"),
        "executable": True,
        "executed": True,
        "recovery_status": "payment_link_created",
        "payment_link_id": execution_result.get("payment_link_id"),
        "test_mode": execution_result.get("test_mode", True),
    }
    if include_url:
        entry["payment_link_url"] = execution_result.get("payment_link_url")
    return _append_entry(entry)


def log_reviewer_decision(
    *,
    case_id: str,
    decision: str,
    lifecycle_status: str,
) -> dict:
    return _append_entry(
        {
            "event_type": "REVIEWER_DECISION",
            "source": "webhook",
            "transaction_id": case_id,
            "decision": decision,
            "lifecycle_status": lifecycle_status,
            "executed": False,
        }
    )


def log_execution_failure(case_id: str, reason: str) -> dict:
    return _append_entry(
        {
            "event_type": "EXECUTION_FAILED",
            "source": "webhook",
            "transaction_id": case_id,
            "reason": reason,
            "executed": False,
        }
    )


def log_webhook_captured(
    *,
    case_id: str,
    payment_id: str,
    amount_rupees: float,
    matched: bool,
) -> dict | None:
    if not matched:
        return None

    return _append_entry(
        {
            "event_type": "WEBHOOK_PAYMENT_CAPTURED",
            "source": "webhook",
            "transaction_id": case_id,
            "razorpay_payment_id": payment_id,
            "amount_rupees": amount_rupees,
            "matched": True,
            "executed": True,
            "recovery_status": "captured",
        }
    )


def has_executed_recovery(transaction_id: str) -> bool:
    """Return True if a RECOVERY_EXECUTED audit entry exists for this case.

    Scans the audit log from the tail so recent executions are found
    instantly without reading the entire file.
    """
    if not transaction_id or not AUDIT_FILE.exists():
        return False

    try:
        lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if (
            entry.get("event_type") == "RECOVERY_EXECUTED"
            and entry.get("transaction_id") == transaction_id
        ):
            return True

    return False


def list_audit_entries(limit: int = 50) -> list[dict]:
    if not AUDIT_FILE.exists():
        return []

    lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(_sanitize_entry(json.loads(line)))
        except json.JSONDecodeError:
            continue

    return list(reversed(entries))


def _count_lifecycle_statuses(db_path: Path) -> dict[str, int]:
    if not db_path.exists():
        return {}

    counts: dict[str, int] = {}
    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(recovery_cases)")
        }
        # The first webhook-aware release did not have lifecycle_status. Keep
        # existing local demo databases usable when metrics are opened before a
        # new webhook event triggers the regular schema migration.
        if "lifecycle_status" not in columns:
            connection.execute(
                "ALTER TABLE recovery_cases ADD COLUMN lifecycle_status "
                "TEXT NOT NULL DEFAULT 'PENDING_REVIEW'"
            )
        rows = connection.execute(
            "SELECT lifecycle_status, COUNT(*) FROM recovery_cases GROUP BY lifecycle_status"
        ).fetchall()
        for status, count in rows:
            counts[str(status)] = int(count)
    return counts


def get_recovery_metrics(revenue_at_risk: dict, *, db_path: Path | None = None) -> dict:
    entries = list_audit_entries(limit=10_000)

    analyzed_ids: set[str] = set()
    approved_ids: set[str] = set()
    blocked_ids: set[str] = set()
    recovered_ids: set[str] = set()
    ai_actions: dict[str, int] = {}

    approved_amount = 0.0
    blocked_amount = 0.0
    recovered_amount = 0.0
    links_created = 0
    webhook_events = 0

    for entry in entries:
        event_type = entry.get("event_type")
        transaction_id = entry.get("transaction_id")
        amount = float(entry.get("amount_rupees", 0) or 0)

        if entry.get("source") == "webhook":
            webhook_events += 1

        if event_type == "RECOVERY_ANALYSIS" and transaction_id:
            analyzed_ids.add(transaction_id)
            action = (entry.get("recommendation") or {}).get("action")
            if action:
                ai_actions[action] = ai_actions.get(action, 0) + 1
            if entry.get("executable"):
                approved_ids.add(transaction_id)
                approved_amount += amount
            else:
                blocked_ids.add(transaction_id)
                blocked_amount += amount

        if event_type == "RECOVERY_EXECUTED":
            links_created += 1

        if event_type == "WEBHOOK_PAYMENT_CAPTURED" and entry.get("matched") and transaction_id:
            recovered_ids.add(transaction_id)
            recovered_amount += amount

        if event_type == "RECOVERY_SIMULATED" and transaction_id:
            recovered_ids.add(transaction_id)
            recovered_amount += amount

    lifecycle_counts = _count_lifecycle_statuses(
        db_path or BASE_DIR / "recovery_cases.db"
    )

    audit_failed_count = len(analyzed_ids)
    failed_count = audit_failed_count if audit_failed_count > 0 else int(revenue_at_risk.get("failed_transaction_count", 0) or 0)

    total_at_risk = float(revenue_at_risk.get("total_revenue_at_risk", 0) or 0)
    if total_at_risk == 0.0 and (approved_amount + blocked_amount) > 0:
        total_at_risk = approved_amount + blocked_amount

    recovery_rate = (
        round((recovered_amount / total_at_risk) * 100, 2)
        if total_at_risk > 0
        else 0.0
    )

    return {
        "total_failed_transactions": failed_count,
        "revenue_at_risk_rupees": total_at_risk,
        "cases_analyzed": len(analyzed_ids),
        "ai_recommendations_by_action": ai_actions,
        "policy_approved_cases": len(approved_ids),
        "policy_blocked_cases": len(blocked_ids),
        "pending_review_count": lifecycle_counts.get("PENDING_REVIEW", 0),
        "approved_count": lifecycle_counts.get("APPROVED", 0),
        "rejected_count": lifecycle_counts.get("REJECTED", 0),
        "policy_blocked_count": lifecycle_counts.get("POLICY_BLOCKED", 0),
        "payment_links_created": links_created,
        "captured_cases": lifecycle_counts.get("PAYMENT_CAPTURED", 0),
        "recovered_cases": len(recovered_ids),
        "recovered_amount_rupees": round(recovered_amount, 2),
        "recovery_rate_percent": recovery_rate,
        "approved_amount_rupees": round(approved_amount, 2),
        "blocked_amount_rupees": round(blocked_amount, 2),
        "audit_entry_count": len(entries),
        "webhook_event_count": webhook_events,
    }
