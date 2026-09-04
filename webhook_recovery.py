"""Safe processing for Razorpay payment webhooks using the shared recovery pipeline."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from backend.app.constants import (
    AI_AUTO_APPROVAL_FAILURE_REASONS,
    AI_AUTO_APPROVAL_LIMIT_RUPEES,
    LIFECYCLE_APPROVED,
    LIFECYCLE_EXECUTION_FAILED,
    LIFECYCLE_LINK_CREATED,
    LIFECYCLE_PAYMENT_CAPTURED,
    LIFECYCLE_PENDING_REVIEW,
    LIFECYCLE_POLICY_BLOCKED,
    LIFECYCLE_REJECTED,
)
from backend.app.services.audit_service import (
    log_executed_recovery,
    log_execution_failure,
    log_recovery_analysis,
    log_reviewer_decision,
    log_webhook_captured,
)
from backend.app.services.ai_decision_service import recommend_with_fallback
from backend.app.services.decision_service import decide_recovery_action
from backend.app.services.policy_service import (
    can_auto_approve_ai,
    evaluate_policy,
)
from backend.app.services.recovery_service import calculate_recovery_score
from backend.app.services.razorpay_execution_service import (
    ExecutionError,
    execute_payment_link_recovery,
)
from backend.app.services.webhook_mapper import payment_to_transaction


# ---------------------------------------------------------------------------
# Legacy deterministic auto-recovery limit.
#
# Kept only for backwards compatibility with callers of run_auto_recovery().
# The webhook flow uses the stricter AI approval gate below, and automatic
# execution is always an explicit ENABLE_AUTO_RECOVERY opt-in.
# ---------------------------------------------------------------------------

AUTO_RECOVERY_LIMIT_RUPEES = AI_AUTO_APPROVAL_LIMIT_RUPEES

AUTO_RECOVERY_FAILURE_REASONS = AI_AUTO_APPROVAL_FAILURE_REASONS


def _database_path() -> Path:
    """Return configured SQLite database path."""

    return Path(
        os.getenv(
            "RECOVERY_DB_PATH",
            "recovery_cases.db",
        )
    )


def _connect() -> sqlite3.Connection:
    """Open the database and ensure required tables/columns exist."""

    connection = sqlite3.connect(
        _database_path()
    )

    # ------------------------------------------------------------------
    # Webhook idempotency table
    # ------------------------------------------------------------------

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            payment_id TEXT,
            received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ------------------------------------------------------------------
    # Recovery cases table
    # ------------------------------------------------------------------

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS recovery_cases (
            case_id TEXT PRIMARY KEY,
            payment_id TEXT NOT NULL,
            order_id TEXT,
            payment_status TEXT NOT NULL,
            amount_paise INTEGER NOT NULL,
            failure_reason TEXT,
            failure_event_count INTEGER NOT NULL DEFAULT 0,
            recovery_score INTEGER,
            recommended_action TEXT,
            policy_decision TEXT,
            policy_reason TEXT,
            lifecycle_status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
            review_status TEXT NOT NULL DEFAULT 'PENDING',
            review_note TEXT,
            reviewed_at TEXT,
            recovery_link_status TEXT NOT NULL DEFAULT 'NOT_REQUESTED',
            recovery_link_id TEXT,
            recovery_link_reference_id TEXT,
            recovery_link_created_at TEXT,
            customer_contact TEXT,
            source TEXT NOT NULL DEFAULT 'webhook',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ------------------------------------------------------------------
    # Lightweight schema migrations for existing databases.
    # ------------------------------------------------------------------

    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(recovery_cases)"
        )
    }

    migrations = {
        "order_id": "TEXT",
        "recovery_score": "INTEGER",
        "lifecycle_status": (
            "TEXT NOT NULL DEFAULT 'PENDING_REVIEW'"
        ),
        "recovery_link_reference_id": "TEXT",
        "customer_contact": "TEXT",
        "source": "TEXT NOT NULL DEFAULT 'webhook'",
        "review_status": (
            "TEXT NOT NULL DEFAULT 'PENDING'"
        ),
        "review_note": "TEXT",
        "reviewed_at": "TEXT",
        "recovery_link_status": (
            "TEXT NOT NULL DEFAULT 'NOT_REQUESTED'"
        ),
        "recovery_link_id": "TEXT",
        "recovery_link_created_at": "TEXT",
    }

    for column, definition in migrations.items():
        if column not in existing_columns:
            connection.execute(
                f"ALTER TABLE recovery_cases "
                f"ADD COLUMN {column} {definition}"
            )

    return connection


def make_event_id(
    header_event_id: str | None,
    event_type: str,
    payment_id: str | None,
    raw_body: bytes,
) -> str:
    """Create an idempotency key for a webhook."""

    if header_event_id:
        return header_event_id

    digest = hashlib.sha256(
        raw_body
    ).hexdigest()

    return (
        f"{event_type}:"
        f"{payment_id or 'unknown'}:"
        f"{digest[:32]}"
    )


def is_auto_recovery_enabled() -> bool:
    """Return whether the legacy auto-recovery switch is enabled."""

    return (
        os.getenv(
            "ENABLE_AUTO_RECOVERY",
            "false",
        )
        .strip()
        .lower()
        == "true"
    )


def _auto_recovery_eligible(
    amount_paise: int,
    failure_reason: str,
    policy: dict,
) -> bool:
    """Check eligibility for the legacy deterministic path."""

    return (
        is_auto_recovery_enabled()
        and amount_paise
        <= AUTO_RECOVERY_LIMIT_RUPEES * 100
        and failure_reason
        in AUTO_RECOVERY_FAILURE_REASONS
        and policy.get("decision")
        == "ALLOW"
    )


def _record_event(
    connection: sqlite3.Connection,
    event_id: str,
    event_type: str,
    payment_id: str | None,
) -> bool:
    """Record a webhook event once."""

    try:
        connection.execute(
            """
            INSERT INTO webhook_events (
                event_id,
                event_type,
                payment_id
            )
            VALUES (?, ?, ?)
            """,
            (
                event_id,
                event_type,
                payment_id,
            ),
        )

        return True

    except sqlite3.IntegrityError:
        return False


def _initial_lifecycle(
    policy: dict,
) -> str:
    """Map initial policy decision to lifecycle status."""

    if policy.get("decision") in {
        "DENY",
        "BLOCK",
    }:
        return LIFECYCLE_POLICY_BLOCKED

    return LIFECYCLE_PENDING_REVIEW


def _build_webhook_analysis(
    transaction: dict,
) -> dict:
    """
    Run both rule-based and AI/fallback recommendations.

    AI is authoritative for the recommendation path.

    The deterministic policy engine remains authoritative
    for execution safety.
    """

    # ------------------------------------------------------------------
    # Rule-based recommendation
    # ------------------------------------------------------------------

    rule_recommendation = decide_recovery_action(
        transaction
    )

    rule_outcome = evaluate_policy(
        transaction,
        rule_recommendation,
    )

    # ------------------------------------------------------------------
    # AI recommendation
    # ------------------------------------------------------------------

    ai_recommendation = recommend_with_fallback(
        transaction
    )

    ai_outcome = evaluate_policy(
        transaction,
        ai_recommendation,
    )

    return {
        "transaction": transaction,
        "rule_based": {
            "recommendation": rule_recommendation,
            "outcome": rule_outcome,
        },
        "ai": {
            "recommendation": ai_recommendation,
            "outcome": ai_outcome,
        },
        "authoritative": ai_outcome,
    }


def process_failed_payment(
    event_id: str,
    payment: dict,
    *,
    source: str = "webhook",
    previous_recovery_attempts_override: int | None = None,
) -> dict:
    """
    Record and classify a failed payment.

    Low-risk AI-approved cases may be automatically executed only when
    ENABLE_AUTO_RECOVERY=true. Otherwise every non-blocked case waits for a
    human reviewer.

    Everything else remains pending human review or policy blocked.

    This function is idempotent with respect to webhook events.
    """

    payment_id = payment.get("id")
    order_id = payment.get("order_id")
    case_id = order_id or payment_id

    if not payment_id or not case_id:
        raise ValueError(
            "Razorpay payment event is missing an id or order_id."
        )

    try:
        amount_paise = int(
            payment.get(
                "amount",
                0,
            )
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Razorpay payment amount is invalid."
        ) from exc

    with _connect() as connection:

        # --------------------------------------------------------------
        # Webhook idempotency
        # --------------------------------------------------------------

        if not _record_event(
            connection,
            event_id,
            "payment.failed",
            payment_id,
        ):
            return {
                "duplicate": True,
                "case_id": case_id,
            }

        # --------------------------------------------------------------
        # Existing failure count
        # --------------------------------------------------------------

        previous = connection.execute(
            """
            SELECT failure_event_count
            FROM recovery_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if previous_recovery_attempts_override is None:
            failure_event_count = (previous[0] if previous else 0) + 1
            previous_attempts = max(failure_event_count - 1, 0)
        else:
            previous_attempts = max(int(previous_recovery_attempts_override), 0)
            failure_event_count = previous_attempts + 1

        # --------------------------------------------------------------
        # Convert Razorpay payment into internal transaction format.
        # --------------------------------------------------------------

        transaction = payment_to_transaction(
            payment,
            case_id=case_id,
            previous_recovery_attempts=previous_attempts,
        )

        # --------------------------------------------------------------
        # Recovery scoring
        # --------------------------------------------------------------

        score = calculate_recovery_score(
            transaction
        )

        transaction.update(score)

        # --------------------------------------------------------------
        # Rule + AI analysis
        # --------------------------------------------------------------

        analysis_result = _build_webhook_analysis(
            transaction
        )

        authoritative = analysis_result[
            "authoritative"
        ]

        recommendation = analysis_result[
            "ai"
        ]["recommendation"]

        outcome = authoritative

        policy = outcome["policy"]

        failure_reason = transaction[
            "failure_reason"
        ]

        # --------------------------------------------------------------
        # AI automatic-approval gate
        # --------------------------------------------------------------

        ai_auto_approved = False

        ai_auto_approval_reason = (
            "AI auto-approval was not evaluated."
        )

        if not is_auto_recovery_enabled():
            ai_auto_approval_reason = (
                "Automatic recovery is disabled by ENABLE_AUTO_RECOVERY."
            )
        elif recommendation.get("source") == "ai":
            (
                ai_auto_approved,
                ai_auto_approval_reason,
            ) = can_auto_approve_ai(
                transaction,
                recommendation,
                policy,
            )
        else:
            # AI call failed (rule_based_fallback). If the fallback itself
            # recommends CREATE_PAYMENT_LINK with no risk flags, run it
            # through the same can_auto_approve_ai guardrails.
            # We temporarily spoof source="ai" only for this check;
            # the audit still records the real source.
            fallback_action = str(
                recommendation.get("action", "")
            ).upper()
            fallback_risk_flags = recommendation.get(
                "risk_flags", []
            )
            if (
                fallback_action == "CREATE_PAYMENT_LINK"
                and not fallback_risk_flags
            ):
                (
                    ai_auto_approved,
                    ai_auto_approval_reason,
                ) = can_auto_approve_ai(
                    transaction,
                    {**recommendation, "source": "ai"},
                    policy,
                )
                if ai_auto_approved:
                    ai_auto_approval_reason = (
                        "Rule-based fallback passed AI guardrails "
                        "(Gemini unavailable)."
                    )
            else:
                ai_auto_approval_reason = (
                    "Rule-based fallback did not recommend "
                    "CREATE_PAYMENT_LINK; human review required."
                )

        # --------------------------------------------------------------
        # Initial lifecycle
        # --------------------------------------------------------------

        lifecycle = _initial_lifecycle(
            policy
        )

        if ai_auto_approved:
            lifecycle = LIFECYCLE_APPROVED

        # --------------------------------------------------------------
        # Audit analysis
        # --------------------------------------------------------------

        audit = log_recovery_analysis(
            transaction,
            {
                **analysis_result,
                "ai_auto_approval": {
                    "approved": ai_auto_approved,
                    "reason": ai_auto_approval_reason,
                },
            },
            analysis_mode="ai",
            source=source,
        )

        # --------------------------------------------------------------
        # Store / update recovery case
        # --------------------------------------------------------------

        connection.execute(
            """
            INSERT INTO recovery_cases (
                case_id,
                payment_id,
                order_id,
                payment_status,
                amount_paise,
                failure_reason,
                failure_event_count,
                recovery_score,
                recommended_action,
                policy_decision,
                policy_reason,
                lifecycle_status,
                review_status,
                customer_contact,
                source,
                updated_at
            )
            VALUES (
                ?,
                ?,
                ?,
                'failed',
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                CURRENT_TIMESTAMP
            )

            ON CONFLICT(case_id) DO UPDATE SET
                payment_id = excluded.payment_id,
                order_id = excluded.order_id,
                payment_status = excluded.payment_status,
                amount_paise = excluded.amount_paise,
                failure_reason = excluded.failure_reason,
                failure_event_count =
                    excluded.failure_event_count,
                recovery_score =
                    excluded.recovery_score,
                recommended_action =
                    excluded.recommended_action,
                policy_decision =
                    excluded.policy_decision,
                policy_reason =
                    excluded.policy_reason,
                lifecycle_status =
                    excluded.lifecycle_status,
                review_status =
                    excluded.review_status,
                customer_contact =
                    COALESCE(
                        excluded.customer_contact,
                        customer_contact
                    ),
                source = excluded.source,
                updated_at =
                    CURRENT_TIMESTAMP
            """,
            (
                case_id,
                payment_id,
                order_id,
                amount_paise,
                failure_reason,
                failure_event_count,
                score.get("recovery_score"),
                recommendation.get(
                    "action",
                    recommendation.get(
                        "recommended_action",
                        "",
                    ),
                ),
                policy["decision"],
                policy["reason"],
                lifecycle,
                (
                    "APPROVE"
                    if ai_auto_approved
                    else "PENDING"
                ),
                payment.get("contact"),
                source,
            ),
        )

    # ------------------------------------------------------------------
    # Build response
    # ------------------------------------------------------------------

    result = {
        "duplicate": False,
        "case_id": case_id,
        "source": source,
        "transaction": transaction,
        "score": score,
        "recommendation": recommendation,
        "policy": policy,
        "outcome": outcome,
        "analysis": analysis_result,
        "lifecycle_status": lifecycle,
        "audit": audit,
        "ai_auto_approved": ai_auto_approved,
        "ai_auto_approval_reason": (
            ai_auto_approval_reason
        ),
        "auto_recovery_eligible": _auto_recovery_eligible(
            amount_paise,
            failure_reason,
            policy,
        ),
    }

    # ------------------------------------------------------------------
    # Execute immediately only after the explicitly enabled AI auto-approval.
    # ------------------------------------------------------------------

    if ai_auto_approved:

        execution_result = execute_webhook_case(
            case_id,
            execution_mode="ai_auto_approved",
        )

        result["auto_execution"] = execution_result

        if execution_result.get("executed"):
            result["lifecycle_status"] = (
                LIFECYCLE_LINK_CREATED
            )
        else:
            result["lifecycle_status"] = (
                LIFECYCLE_EXECUTION_FAILED
            )

        # AI auto-approval acts as an explicit approval for this case.
        result["review_status"] = "APPROVE"

    return result


def process_captured_payment(
    event_id: str,
    payment: dict,
    *,
    recovery_reference_id: str | None = None,
) -> dict:
    """Match captured payment to a recovery case."""

    payment_id = payment.get("id")
    order_id = payment.get("order_id")
    case_id = order_id or payment_id

    if not payment_id or not case_id:
        raise ValueError(
            "Razorpay payment event is missing an id or order_id."
        )

    amount_rupees = (
        int(
            payment.get(
                "amount",
                0,
            )
            or 0
        )
        / 100
    )

    notes = payment.get("notes") or {}

    reference_id = (
        recovery_reference_id
        or payment.get("description")
        or notes.get("reference_id")
    )

    with _connect() as connection:

        # --------------------------------------------------------------
        # Webhook idempotency
        # --------------------------------------------------------------

        if not _record_event(
            connection,
            event_id,
            "payment.captured",
            payment_id,
        ):
            return {
                "duplicate": True,
                "case_id": case_id,
            }

        connection.row_factory = sqlite3.Row

        # --------------------------------------------------------------
        # Match the captured payment to the recovery case.
        # --------------------------------------------------------------

        case = connection.execute(
            """
            SELECT
                case_id,
                lifecycle_status,
                recovery_link_reference_id,
                amount_paise
            FROM recovery_cases
            WHERE case_id = ?
               OR order_id = ?
               OR payment_id = ?
               OR recovery_link_reference_id = ?
            """,
            (
                case_id,
                case_id,
                payment_id,
                reference_id,
            ),
        ).fetchone()

        if case is None:
            return {
                "duplicate": False,
                "case_id": case_id,
                "matched": False,
                "audit": None,
            }

        # --------------------------------------------------------------
        # Only a link-created recovery can be counted as recovered.
        # --------------------------------------------------------------

        if (
            case["lifecycle_status"]
            != LIFECYCLE_LINK_CREATED
        ):
            return {
                "duplicate": False,
                "case_id": case["case_id"],
                "matched": False,
                "reason": (
                    "Captured payment does not match "
                    "a link-created recovery case."
                ),
                "audit": None,
            }

        connection.execute(
            """
            UPDATE recovery_cases
            SET payment_status = 'captured',
                lifecycle_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE case_id = ?
            """,
            (
                LIFECYCLE_PAYMENT_CAPTURED,
                case["case_id"],
            ),
        )

    audit = log_webhook_captured(
        case_id=case["case_id"],
        payment_id=payment_id,
        amount_rupees=amount_rupees,
        matched=True,
    )

    return {
        "duplicate": False,
        "case_id": case["case_id"],
        "matched": True,
        "audit": audit,
    }


def list_recovery_cases() -> list[dict]:
    """Return sanitized recovery cases without PII."""

    with _connect() as connection:

        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT
                case_id,
                payment_id,
                order_id,
                payment_status,
                amount_paise,
                failure_reason,
                failure_event_count,
                recovery_score,
                recommended_action,
                policy_decision,
                policy_reason,
                lifecycle_status,
                review_status,
                reviewed_at,
                recovery_link_status,
                recovery_link_id,
                recovery_link_created_at,
                source,
                updated_at
            FROM recovery_cases
            ORDER BY updated_at DESC
            """
        ).fetchall()

    return [
        {
            "case_id": row["case_id"],
            "payment_id": row["payment_id"],
            "order_id": row["order_id"],
            "payment_status": row["payment_status"],
            "amount_rupees": (
                row["amount_paise"] / 100
            ),
            "failure_reason": row["failure_reason"],
            "failure_event_count": row[
                "failure_event_count"
            ],
            "recovery_score": row[
                "recovery_score"
            ],
            "opportunity": (
                "HIGH"
                if (row["recovery_score"] or 0) >= 70
                else "MEDIUM"
                if (row["recovery_score"] or 0) >= 40
                else "LOW"
            ),
            "recommended_action": row[
                "recommended_action"
            ],
            "policy_decision": row[
                "policy_decision"
            ],
            "policy_reason": row[
                "policy_reason"
            ],
            "lifecycle_status": row[
                "lifecycle_status"
            ],
            "review_status": row[
                "review_status"
            ],
            "reviewed_at": row[
                "reviewed_at"
            ],
            "recovery_link_status": row[
                "recovery_link_status"
            ],
            "recovery_link_id": row[
                "recovery_link_id"
            ],
            "recovery_link_created_at": row[
                "recovery_link_created_at"
            ],
            "source": row["source"],
            "updated_at": row[
                "updated_at"
            ],
        }
        for row in rows
    ]


def get_case(
    case_id: str,
) -> sqlite3.Row | None:
    """Return a recovery case."""

    with _connect() as connection:

        connection.row_factory = sqlite3.Row

        return connection.execute(
            """
            SELECT *
            FROM recovery_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()


def record_review(
    case_id: str,
    decision: str,
    note: str | None = None,
    approved_action: str | None = None,
) -> dict:
    """
    Record reviewer approve/reject.

    Human approval may explicitly choose CREATE_PAYMENT_LINK
    for a case that requires human review.

    It does not directly call Razorpay.
    """

    review_status = decision.upper()

    if review_status not in {
        "APPROVE",
        "REJECT",
    }:
        raise ValueError(
            "Review decision must be approve or reject."
        )

    if approved_action:
        approved_action = (
            str(approved_action)
            .strip()
            .upper()
        )

    with _connect() as connection:

        connection.row_factory = sqlite3.Row

        case = connection.execute(
            """
            SELECT *
            FROM recovery_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()

        if case is None:
            raise LookupError(
                "Recovery case not found."
            )

        if case["payment_status"] != "failed":
            raise ValueError(
                "Only failed payments can be reviewed."
            )

        if case["lifecycle_status"] in {
            LIFECYCLE_LINK_CREATED,
            LIFECYCLE_PAYMENT_CAPTURED,
            LIFECYCLE_REJECTED,
        }:
            raise ValueError(
                "Case is no longer reviewable."
            )

        # --------------------------------------------------------------
        # Rejected
        # --------------------------------------------------------------

        if review_status == "REJECT":

            lifecycle = LIFECYCLE_REJECTED

            connection.execute(
                """
                UPDATE recovery_cases
                SET
                    review_status = ?,
                    review_note = ?,
                    reviewed_at = CURRENT_TIMESTAMP,
                    lifecycle_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE case_id = ?
                """,
                (
                    review_status,
                    note,
                    lifecycle,
                    case_id,
                ),
            )

        # --------------------------------------------------------------
        # Approved
        # --------------------------------------------------------------

        else:

            final_action = (
                approved_action
                or case["recommended_action"]
            )

            if final_action != "CREATE_PAYMENT_LINK":
                raise ValueError(
                    "Human approval must specify "
                    "CREATE_PAYMENT_LINK for payment-link execution."
                )

            if case["policy_decision"] not in {
                "ALLOW",
                "REVIEW",
            }:
                raise ValueError(
                    "A policy-blocked action cannot be approved."
                )

            lifecycle = LIFECYCLE_APPROVED

            connection.execute(
                """
                UPDATE recovery_cases
                SET
                    review_status = 'APPROVE',
                    review_note = ?,
                    reviewed_at = CURRENT_TIMESTAMP,
                    lifecycle_status = ?,
                    recommended_action = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE case_id = ?
                """,
                (
                    note,
                    lifecycle,
                    final_action,
                    case_id,
                ),
            )

            approved_action = final_action

    audit = log_reviewer_decision(
        case_id=case_id,
        decision=review_status,
        lifecycle_status=lifecycle,
    )

    return {
        "case_id": case_id,
        "review_status": review_status,
        "lifecycle_status": lifecycle,
        "recommended_action": (
            approved_action
            or case["recommended_action"]
        ),
        "approved_action": (
            approved_action
            if review_status == "APPROVE"
            else None
        ),
        "executed": False,
        "audit": audit,
    }


def _claim_execution(
    case_id: str,
) -> bool:
    """
    Atomically claim a case for execution.

    This prevents duplicate payment-link creation.
    """

    with _connect() as connection:

        cursor = connection.execute(
            """
            UPDATE recovery_cases
            SET
                recovery_link_status = 'IN_PROGRESS',
                updated_at = CURRENT_TIMESTAMP
            WHERE case_id = ?
              AND lifecycle_status = ?
              AND review_status = 'APPROVE'
              AND policy_decision IN ('ALLOW', 'REVIEW')
              AND recommended_action = 'CREATE_PAYMENT_LINK'
              AND recovery_link_status = 'NOT_REQUESTED'
              AND payment_status = 'failed'
            """,
            (
                case_id,
                LIFECYCLE_APPROVED,
            ),
        )

    return cursor.rowcount == 1


def _record_link_result(
    case_id: str,
    *,
    status: str,
    link_id: str | None = None,
    reference_id: str | None = None,
    lifecycle: str | None = None,
) -> None:
    """Persist payment-link execution result."""

    with _connect() as connection:

        connection.execute(
            """
            UPDATE recovery_cases
            SET
                recovery_link_status = ?,
                recovery_link_id =
                    COALESCE(
                        ?,
                        recovery_link_id
                    ),
                recovery_link_reference_id =
                    COALESCE(
                        ?,
                        recovery_link_reference_id
                    ),
                recovery_link_created_at =
                    CASE
                        WHEN ? = 'CREATED'
                        THEN CURRENT_TIMESTAMP
                        ELSE recovery_link_created_at
                    END,
                lifecycle_status =
                    COALESCE(
                        ?,
                        lifecycle_status
                    ),
                updated_at = CURRENT_TIMESTAMP
            WHERE case_id = ?
            """,
            (
                status,
                link_id,
                reference_id,
                status,
                lifecycle,
                case_id,
            ),
        )


def execute_webhook_case(
    case_id: str,
    *,
    execution_mode: str = "human_approved",
) -> dict:
    """
    Create one Test Mode payment link for an approved webhook case.

    Supported modes:

        human_approved
        ai_auto_approved
        rule_based_auto
    """

    case = get_case(
        case_id
    )

    if case is None:
        raise LookupError(
            "Recovery case not found."
        )

    # ------------------------------------------------------------------
    # Case must already be approved.
    # ------------------------------------------------------------------

    if (
        case["lifecycle_status"]
        != LIFECYCLE_APPROVED
    ):
        return {
            "executed": False,
            "reason": (
                "Case must be APPROVED before "
                "execution "
                f"(current: {case['lifecycle_status']})."
            ),
        }

    # ------------------------------------------------------------------
    # Policy must permit the action.
    # ------------------------------------------------------------------

    if case["policy_decision"] not in {
        "ALLOW",
        "REVIEW",
    }:
        return {
            "executed": False,
            "reason": case["policy_reason"],
        }

    # ------------------------------------------------------------------
    # Only payment-link recovery can execute here.
    # ------------------------------------------------------------------

    if (
        case["recommended_action"]
        != "CREATE_PAYMENT_LINK"
    ):
        return {
            "executed": False,
            "reason": (
                "Only CREATE_PAYMENT_LINK cases "
                "can be executed via payment link."
            ),
        }

    # ------------------------------------------------------------------
    # Atomic execution claim.
    # ------------------------------------------------------------------

    if not _claim_execution(
        case_id
    ):
        return {
            "executed": False,
            "reason": (
                "Case is not eligible or a link "
                "was already requested."
            ),
        }

    # ------------------------------------------------------------------
    # Customer contact is required by the execution layer.
    # ------------------------------------------------------------------

    contact = case["customer_contact"]

    if not contact:
        _record_link_result(
            case_id,
            status="BLOCKED",
            lifecycle=LIFECYCLE_EXECUTION_FAILED,
        )

        log_execution_failure(
            case_id,
            "Customer contact is required.",
        )

        return {
            "executed": False,
            "reason": "Customer contact is required.",
        }

    # ------------------------------------------------------------------
    # Reconstruct the transaction from stored case data.
    # ------------------------------------------------------------------

    transaction = {
        "transaction_id": case_id,
        "amount": (
            case["amount_paise"] / 100
        ),
        "payment_status": "failed",
        "failure_reason": case[
            "failure_reason"
        ],
        "previous_recovery_attempts": max(
            case["failure_event_count"] - 1,
            0,
        ),
    }

    # ------------------------------------------------------------------
    # Do NOT ask Gemini again during execution.
    #
    # The approved/stored action is the source of truth.
    # ------------------------------------------------------------------

    recommendation = {
        "action": "CREATE_PAYMENT_LINK",
        "confidence": 1.0,
        "risk_flags": [],
    }

    outcome = evaluate_policy(
        transaction,
        recommendation,
    )

    # ------------------------------------------------------------------
    # Human approval may authorize a REVIEW case.
    #
    # AI auto-approved cases should already have policy=ALLOW.
    # ------------------------------------------------------------------

    if (
        execution_mode == "human_approved"
        and case["policy_decision"] == "REVIEW"
    ):
        outcome = {
            "policy": {
                "decision": "REVIEW",
                "reason": (
                    "Human reviewer explicitly approved "
                    "CREATE_PAYMENT_LINK."
                ),
            },
            "decision": "REVIEW",
            "reason": (
                "Human reviewer explicitly approved "
                "CREATE_PAYMENT_LINK."
            ),
            "final_action": "CREATE_PAYMENT_LINK",
            "final_status": "APPROVED",
            "final_reason": (
                "Human reviewer approved payment-link recovery."
            ),
            "executable": True,
            "executed": False,
        }

    # ------------------------------------------------------------------
    # Final execution guard.
    # ------------------------------------------------------------------

    if not outcome.get(
        "executable"
    ):
        _record_link_result(
            case_id,
            status="BLOCKED",
            lifecycle=LIFECYCLE_EXECUTION_FAILED,
        )

        failure_reason = str(
            outcome.get(
                "final_reason",
                "Policy blocked.",
            )
        )

        log_execution_failure(
            case_id,
            failure_reason,
        )

        return {
            "executed": False,
            "reason": failure_reason,
        }

    # ------------------------------------------------------------------
    # Execute against Razorpay Test Mode.
    # ------------------------------------------------------------------

    try:

        execution_result = (
            execute_payment_link_recovery(
                transaction,
                customer_contact=contact,
            )
        )

    except ExecutionError as exc:

        _record_link_result(
            case_id,
            status="FAILED",
            lifecycle=LIFECYCLE_EXECUTION_FAILED,
        )

        log_execution_failure(
            case_id,
            str(exc),
        )

        return {
            "executed": False,
            "reason": str(exc),
        }

    # ------------------------------------------------------------------
    # Audit successful execution.
    # ------------------------------------------------------------------

    audit = log_executed_recovery(
        transaction,
        outcome,
        execution_result,
        analysis_mode=execution_mode,
        source=case["source"],
        include_url=False,
    )

    # ------------------------------------------------------------------
    # Store link details.
    # ------------------------------------------------------------------

    _record_link_result(
        case_id,
        status="CREATED",
        link_id=execution_result.get(
            "payment_link_id"
        ),
        reference_id=execution_result.get(
            "reference_id"
        ),
        lifecycle=LIFECYCLE_LINK_CREATED,
    )

    return {
        "executed": True,
        "case_id": case_id,
        "payment_link_id": execution_result.get(
            "payment_link_id"
        ),
        "reference_id": execution_result.get(
            "reference_id"
        ),
        "lifecycle_status": (
            LIFECYCLE_LINK_CREATED
        ),
        "audit": audit,
        "note": (
            "Payment link created in Test Mode. "
            "URL available only in secure "
            "execution response."
        ),
        "payment_link_url": execution_result.get(
            "payment_link_url"
        ),
    }


def run_auto_recovery(
    case_id: str,
    payment: dict,
) -> None:
    """
    Legacy deterministic auto-recovery path.

    Kept for compatibility.

    The current webhook route does not call this function. It remains for
    backwards-compatible direct callers; new automatic execution must use the
    stricter AI approval path in process_failed_payment().
    """

    if not is_auto_recovery_enabled():
        return

    case = get_case(
        case_id
    )

    if case is None:
        return

    if (
        case["amount_paise"]
        > AUTO_RECOVERY_LIMIT_RUPEES * 100
    ):
        return

    if (
        case["failure_reason"]
        not in AUTO_RECOVERY_FAILURE_REASONS
    ):
        return

    if case["policy_decision"] != "ALLOW":
        return

    with _connect() as connection:

        connection.execute(
            """
            UPDATE recovery_cases
            SET
                review_status = 'APPROVE',
                lifecycle_status = ?,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE case_id = ?
              AND lifecycle_status = ?
            """,
            (
                LIFECYCLE_APPROVED,
                case_id,
                LIFECYCLE_PENDING_REVIEW,
            ),
        )

    result = execute_webhook_case(
        case_id,
        execution_mode="rule_based_auto",
    )

    if result.get(
        "executed"
    ):

        print(
            "\nTEST MODE RECOVERY LINK CREATED (auto)"
        )

        print(
            "Case ID:",
            case_id,
        )

        print(
            "Link ID:",
            result.get(
                "payment_link_id"
            ),
        )

    else:

        print(
            "\nAUTO RECOVERY NOT RUN:",
            result.get(
                "reason"
            ),
        )
