"""Quick API health check for local demo."""

import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path) as response:
        return json.loads(response.read().decode())


def main() -> None:
    print("=== HEALTH ===")
    print(get("/health"))

    print("\n=== REVENUE AT RISK ===")
    risk = get("/revenue-at-risk")
    print(
        f"Failed: {risk['failed_transaction_count']}, "
        f"At risk: INR {risk['total_revenue_at_risk']}"
    )

    print("\n=== BATCH RECOVER (first 5) ===")
    batch = get("/batch-recover?limit=5")
    print(json.dumps(batch["summary"], indent=2))

    print("\n=== RECOVER TXN0011 ===")
    recover = get("/recover/TXN0011")
    auth = recover["authoritative"]
    txn = recover["transaction"]
    print(
        f"Score: {txn['recovery_score']}, "
        f"Status: {auth['final_status']}, "
        f"Action: {auth['final_action']}"
    )

    print("\n=== RECOVERY METRICS ===")
    print(json.dumps(get("/recovery-metrics"), indent=2))

    print("\n=== AUDIT TRAIL (last 5) ===")
    audit = get("/audit-trail?limit=5")
    for entry in audit["entries"]:
        print(
            f"- {entry.get('event_type')} | "
            f"{entry.get('source', 'csv')} | "
            f"{entry.get('transaction_id', '')} | "
            f"INR {entry.get('amount_rupees', '')}"
        )


if __name__ == "__main__":
    main()
