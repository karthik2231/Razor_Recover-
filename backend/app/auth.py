"""Reviewer authentication for protected operational endpoints."""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request


def require_review_token(request: Request) -> None:
    """Validate X-Review-Token header against REVIEW_API_TOKEN."""
    configured = os.getenv("REVIEW_API_TOKEN")
    supplied = request.headers.get("X-Review-Token")

    if not configured:
        raise HTTPException(
            status_code=503,
            detail="Recovery review access is not configured.",
        )
    if not supplied or not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="Invalid review token.")
