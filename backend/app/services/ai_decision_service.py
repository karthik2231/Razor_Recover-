"""AI-powered recovery recommendations using the Google GenAI SDK."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from backend.app.constants import (
    AI_AUTO_APPROVAL_FAILURE_REASONS,
    AI_AUTO_APPROVAL_LIMIT_RUPEES,
    AI_AUTO_APPROVAL_MIN_CONFIDENCE,
    LEGACY_ACTION_MAP,
    RECOVERY_ACTIONS,
)
from backend.app.services.decision_service import decide_recovery_action

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

DEFAULT_MODEL = "gemini-3.6-flash"


class AIDecisionError(Exception):
    """Raised when the AI service cannot return a valid recommendation."""


def _get_client() -> genai.Client:
    """Return a fresh Gemini client using the current environment variable."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise AIDecisionError(
            "GEMINI_API_KEY is not configured. "
            "Add it to the project root .env file."
        )

    return genai.Client(api_key=api_key)


def _get_model_name() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _build_prompt(transaction: dict) -> str:
    actions = ", ".join(sorted(RECOVERY_ACTIONS))

    return f"""
You are RazorRecover, an intelligent payment recovery recommendation engine.

Your job is to recommend exactly ONE recovery action.

Transaction context:
- transaction_id: {transaction.get("transaction_id")}
- amount (INR): {transaction.get("amount")}
- failure_reason: {transaction.get("failure_reason")}
- payment_method: {transaction.get("payment_method")}
- successful_payments: {transaction.get("successful_payments")}
- previous_recovery_attempts: {transaction.get("previous_recovery_attempts")}
- recovery_score: {transaction.get("recovery_score")}
- opportunity: {transaction.get("opportunity")}

IMPORTANT DECISION RULES:

1. Valid recovery failure reasons include:
   - payment_failed
   - bank_timeout
   - network_error
   - upi_failure

2. RECOVERY ELIGIBILITY:
   - Any transaction with amount > INR 25000 is automatically ineligible for recovery and must not be recommended for a recovery action.
   - For transient technical failures (bank_timeout, network_error, upi_failure, payment_failed) on the first recovery attempt (previous_recovery_attempts == 0) with amount <= INR 25000:
     Recommend: CREATE_PAYMENT_LINK
   - The deterministic policy engine will automatically decide whether to auto-approve (amount <= INR 1000) or require human review (amount > INR 1000 and <= INR 25000).

3. "payment_failed" is an acceptable generic failure reason.
   Do not require a more specific failure reason.

4. Do NOT interpret "payment_failed" as automatically requiring
   HUMAN_REVIEW.

5. The recovery_score does NOT determine whether the transaction
   satisfies the automatic recovery rule.
   A LOW recovery_score does not by itself require HUMAN_REVIEW.

6. Do not invent a different failure reason.

7. Only recommend REQUEST_PAYMENT_METHOD_CHANGE when the transaction
   explicitly indicates a payment-method problem such as:
   - authentication_failed
   - card_declined

8. CREATE_PAYMENT_LINK is the supported action for recovering transactions.
   Do NOT recommend RETRY_PAYMENT as direct server retries are not supported without a payment link.

9. If the transaction has high attempts (>= 3), recommend DO_NOT_CONTACT. If it involves fraud risk or unsupported patterns, recommend HUMAN_REVIEW.

10. Do not invent facts that are not present in the transaction.

11. The deterministic policy engine is the final authority.
    You are only recommending an action.

12. When the recovery conditions in rule 2 are satisfied,
    do NOT return HUMAN_REVIEW merely because the failure reason
    is payment_failed or because the amount is between INR 1000 and INR 5000.

Allowed actions: {actions}

Return ONLY valid JSON with:
- action: one allowed action
- reason: short explanation
- confidence: 0.0 to 1.0
- risk_flags: array of short strings (may be empty)
"""


def _response_schema() -> types.Schema:
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "action": types.Schema(type=types.Type.STRING),
            "reason": types.Schema(type=types.Type.STRING),
            "confidence": types.Schema(type=types.Type.NUMBER),
            "risk_flags": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
            ),
        },
        required=[
            "action",
            "reason",
            "confidence",
            "risk_flags",
        ],
    )


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIDecisionError("AI returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise AIDecisionError("AI response must be a JSON object.")

    return payload


def _validate_recommendation(payload: dict) -> dict:
    action = str(payload.get("action", "")).strip().upper()
    action = LEGACY_ACTION_MAP.get(action, action)

    if action not in RECOVERY_ACTIONS:
        raise AIDecisionError(
            "AI returned an invalid action. Expected one of: "
            + ", ".join(sorted(RECOVERY_ACTIONS))
        )

    reason = payload.get("reason")

    if not isinstance(reason, str) or not reason.strip():
        raise AIDecisionError("AI response missing a valid reason.")

    try:
        # pyrefly: ignore [bad-argument-type]
        confidence_value = float(payload.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise AIDecisionError(
            "AI response missing a valid confidence score."
        ) from exc

    if not 0.0 <= confidence_value <= 1.0:
        raise AIDecisionError(
            "AI confidence must be between 0.0 and 1.0."
        )

    risk_flags = payload.get("risk_flags")

    if not isinstance(risk_flags, list):
        risk_flags = []

    risk_flags = [str(flag) for flag in risk_flags if flag]

    return {
        "action": action,
        "reason": reason.strip(),
        "confidence": round(confidence_value, 2),
        "risk_flags": risk_flags,
    }


def _normalize_auto_eligible_recommendation(
    transaction: dict,
    recommendation: dict,
) -> dict:
    """Correct an overly conservative AI action for an exact safe subset.

    This does not approve or execute recovery. It only makes the AI's action
    consistent with the configured automatic-recovery criteria; the policy
    service and can_auto_approve_ai() remain authoritative afterwards.
    """

    try:
        amount = float(transaction.get("amount", 0) or 0)
        attempts = int(transaction.get("previous_recovery_attempts", 0) or 0)
        confidence = float(recommendation.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        return recommendation

    failure_reason = str(transaction.get("failure_reason", "")).strip().lower()
    risk_flags = recommendation.get("risk_flags") or []

    eligible = (
        transaction.get("payment_status") == "failed"
        and amount <= AI_AUTO_APPROVAL_LIMIT_RUPEES
        and amount > 0
        and attempts == 0
        and failure_reason in AI_AUTO_APPROVAL_FAILURE_REASONS
        and confidence >= AI_AUTO_APPROVAL_MIN_CONFIDENCE
        and not risk_flags
    )

    if not eligible or recommendation.get("action") == "CREATE_PAYMENT_LINK":
        return recommendation

    return {
        **recommendation,
        "action": "CREATE_PAYMENT_LINK",
        "reason": (
            "Normalized to CREATE_PAYMENT_LINK: the failed payment satisfies "
            "the configured low-risk automatic-recovery criteria."
        ),
        "normalization": "auto_recovery_eligible_action",
    }


def recommend_recovery_action(transaction: dict) -> dict:
    """Return one validated AI recommendation. Raises on failure."""

    client = _get_client()
    model = _get_model_name()

    prompt = _build_prompt(transaction)

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_response_schema(),
                http_options=types.HttpOptions(timeout=30_000),
            ),
        )
    except Exception as exc:
        raise AIDecisionError(
            f"Gemini request failed for model '{model}'."
        ) from exc

    if not response.text:
        raise AIDecisionError("AI returned an empty response.")

    return _validate_recommendation(
        _parse_json_response(response.text)
    )


def recommend_with_fallback(transaction: dict) -> dict:
    """Return AI recommendation or fall back to rule-based / HUMAN_REVIEW."""

    try:
        recommendation = _normalize_auto_eligible_recommendation(
            transaction,
            recommend_recovery_action(transaction),
        )

        return {
            **recommendation,
            "source": "ai",
        }

    except AIDecisionError as exc:
        fallback = decide_recovery_action(transaction)

        return {
            **fallback,
            "source": "rule_based_fallback",
            "ai_failure": str(exc),
        }
