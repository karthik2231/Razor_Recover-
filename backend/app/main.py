from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from backend.app.auth import require_review_token
from backend.app.routes.razorpay import router as razorpay_router
from backend.app.services.ai_decision_service import (
    AIDecisionError,
    recommend_recovery_action,
    recommend_with_fallback,
)
from backend.app.services.audit_service import get_recovery_metrics, list_audit_entries
from backend.app.services.decision_service import decide_recovery_action
from backend.app.services.recovery_pipeline_service import (
    batch_recover,
    execute_recovery,
    recover_transaction,
    simulate_recovery,
)
from backend.app.services.transaction_service import (
    get_all_transactions,
    get_failed_transactions,
    get_revenue_at_risk,
    get_scored_failed_transactions,
    get_high_recovery_opportunities,
    get_recovery_case_by_id,
)


app = FastAPI(
    title="RazorRecover AI",
    description="AI-powered revenue recovery agent",
    version="0.1.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(razorpay_router)


@app.get("/")
def home():
    return {
        "message": "RazorRecover AI API is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/transactions")
def get_transactions():
    return {
        "count": len(get_all_transactions()),
        "transactions": get_all_transactions()
    }


@app.get("/failed-transactions")
def failed_transactions():
    failed = get_failed_transactions()

    return {
        "count": len(failed),
        "transactions": failed
    }


@app.get("/revenue-at-risk")
def revenue_at_risk():
    return get_revenue_at_risk()

@app.get("/recovery-cases")
def recovery_cases():
    cases = get_scored_failed_transactions()

    return {
        "count": len(cases),
        "cases": cases
    }


@app.get("/high-recovery-opportunities")
def high_recovery_opportunities():
    opportunities = get_high_recovery_opportunities()

    return {
        "count": len(opportunities),
        "opportunities": opportunities
    }

@app.get("/analyze/{transaction_id}")
def analyze_transaction(transaction_id: str):
    transaction = get_recovery_case_by_id(transaction_id)

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found or is not a failed transaction"
        )

    decision = decide_recovery_action(transaction)

    return {
        "transaction": transaction,
        "decision": decision
    }


@app.get("/ai-analyze/{transaction_id}")
def ai_analyze_transaction(transaction_id: str):
    transaction = get_recovery_case_by_id(transaction_id)

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found or is not a failed transaction"
        )

    try:
        ai_recommendation = recommend_with_fallback(transaction)
    except AIDecisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="AI recommendation service is temporarily unavailable."
        ) from exc

    return {
        "transaction": transaction,
        "ai_recommendation": ai_recommendation,
        "note": (
            "AI recommendation only. Policy engine has final authority; "
            "no recovery action was executed."
        ),
    }


@app.get("/recover/{transaction_id}")
def recover_transaction_endpoint(transaction_id: str):
    """Full pipeline: score, rule baseline, AI recommendation, policy verdict."""
    transaction = get_recovery_case_by_id(transaction_id)

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found or is not a failed transaction",
        )

    try:
        return recover_transaction(transaction, use_ai=True)
    except AIDecisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Recovery analysis is temporarily unavailable.",
        ) from exc


@app.get("/batch-recover")
def batch_recover_endpoint(
    use_ai: bool = Query(
        default=False,
        description="Use Gemini for each case. Default uses fast rule-based analysis.",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=100,
        description="Optional limit for demo runs, especially when use_ai=true.",
    ),
):
    """Batch recovery analysis with measurable approval/block totals."""
    try:
        return batch_recover(use_ai=use_ai, limit=limit)
    except AIDecisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Batch recovery analysis is temporarily unavailable.",
        ) from exc


@app.get("/audit-trail")
def audit_trail(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
):
    """Return recent recovery analysis and simulation audit entries."""
    require_review_token(request)
    entries = list_audit_entries(limit=limit)
    return {"count": len(entries), "entries": entries}


@app.get("/recovery-metrics")
def recovery_metrics(request: Request):
    """Show measurable recovery results for hackathon demos."""
    require_review_token(request)
    risk = get_revenue_at_risk()
    return get_recovery_metrics(risk)


@app.post("/simulate-recovery/{transaction_id}")
def simulate_recovery_endpoint(
    transaction_id: str,
    use_ai: bool = Query(
        default=False,
        description="Use AI recommendation before policy check. Default uses rules.",
    ),
):
    """Simulate bounded recovery for one policy-approved failed transaction."""
    transaction = get_recovery_case_by_id(transaction_id)

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found or is not a failed transaction",
        )

    try:
        result = simulate_recovery(transaction, use_ai=use_ai)
    except AIDecisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Recovery simulation is temporarily unavailable.",
        ) from exc

    if not result["simulated"]:
        raise HTTPException(
            status_code=403,
            detail=result["reason"],
        )

    return result


@app.post("/execute-recovery/{transaction_id}")
def execute_recovery_endpoint(
    request: Request,
    transaction_id: str,
    use_ai: bool = Query(
        default=False,
        description="Use AI recommendation before policy check. Default uses rules.",
    ),
    customer_contact: str | None = Query(
        default=None,
        description="Customer phone for the payment link. Falls back to DEFAULT_RECOVERY_CONTACT.",
    ),
    customer_email: str | None = Query(
        default=None,
        description="Optional customer email for the payment link.",
    ),
):
    """Create a bounded Razorpay Test Mode payment link when policy approves."""
    require_review_token(request)
    transaction = get_recovery_case_by_id(transaction_id)

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found or is not a failed transaction",
        )

    try:
        result = execute_recovery(
            transaction,
            use_ai=use_ai,
            customer_contact=customer_contact,
            customer_email=customer_email,
        )
    except AIDecisionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Recovery execution is temporarily unavailable.",
        ) from exc

    if not result["executed"]:
        raise HTTPException(
            status_code=403,
            detail=result["reason"],
        )

    return result
