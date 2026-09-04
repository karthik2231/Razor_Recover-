#!/usr/bin/env python
"""Terminal demo for RevenueRescue AI (Test Mode only)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.getenv("DEMO_API_BASE", "http://127.0.0.1:8000")
TOKEN = os.getenv("REVIEW_API_TOKEN", "")


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", headers=_auth())
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


def _post(path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = _auth()
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


def _auth() -> dict:
    if not TOKEN:
        print("Set REVIEW_API_TOKEN in your environment to run the protected demo steps.")
        sys.exit(1)
    return {"X-Review-Token": TOKEN}


def main() -> None:
    print("RevenueRescue AI demo")
    print("=" * 40)

    try:
        print("\n1. Health")
        print(_get("/health"))

        print("\n2. Revenue at risk (CSV analytics)")
        print(_get("/revenue-at-risk"))

        print("\n3. Live webhook cases")
        cases = _get("/webhook-cases")
        print(f"Cases: {cases['count']}")
        for case in cases.get("cases", [])[:5]:
            print(
                f"  - {case['case_id']} | INR {case['amount_rupees']} | "
                f"{case['lifecycle_status']} | policy={case['policy_decision']}"
            )

        print("\n4. Recovery metrics")
        print(json.dumps(_get("/recovery-metrics"), indent=2))

        print("\n5. Recent audit trail")
        audit = _get("/audit-trail?limit=5")
        for entry in audit.get("entries", []):
            print(
                f"  - {entry.get('event_type')} | {entry.get('transaction_id', '-')} | "
                f"INR {entry.get('amount_rupees', '')}"
            )

        pending = [
            case
            for case in cases.get("cases", [])
            if case.get("lifecycle_status") == "PENDING_REVIEW"
            and case.get("policy_decision") == "ALLOW"
        ]
        if pending:
            case_id = pending[0]["case_id"]
            print(f"\n6. Approve pending case {case_id}")
            print(_post(f"/webhook-cases/{case_id}/review", {"decision": "approve"}))

            print(f"\n7. Execute approved case {case_id}")
            try:
                print(_post(f"/webhook-cases/{case_id}/execute"))
            except urllib.error.HTTPError as exc:
                print(f"Execution blocked: {exc.read().decode()}")
        else:
            print("\n6. No pending ALLOW cases to approve/execute in SQLite.")

        print("\nDemo complete.")
    except urllib.error.HTTPError as exc:
        print(f"HTTP error {exc.code}: {exc.read().decode()}")
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Could not reach API at {BASE}. Start the server first.")
        print(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
