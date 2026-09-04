"""Create multiple Razorpay Test Mode payment links for demo data."""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from create_payment_link import create_recovery_payment_link

# Mix of small, medium, and high-value test amounts (₹).
DEFAULT_AMOUNTS = [
    250,
    500,
    750,
    1200,
    1500,
    2500,
    3500,
    5000,
    7500,
    10000,
]


def main() -> None:
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    if not key_id.startswith("rzp_test_"):
        print("ERROR: RAZORPAY_KEY_ID must be a Test Mode key (rzp_test_...).")
        sys.exit(1)

    contact = os.getenv("DEFAULT_RECOVERY_CONTACT", "8610169138")
    email = os.getenv("DEFAULT_RECOVERY_EMAIL", "demo@revenuerescue.test")

    print("Creating Razorpay Test Mode payment links...\n")
    print(f"{'#':<4} {'Amount (INR)':<12} {'Reference ID':<22} {'Payment link'}")
    print("-" * 90)

    created = []
    for index, amount in enumerate(DEFAULT_AMOUNTS, start=1):
        transaction_id = f"TXN_TEST_{uuid.uuid4().hex[:8]}"
        try:
            link = create_recovery_payment_link(
                transaction_id=transaction_id,
                amount=amount,
                customer_name=f"Test Customer {index}",
                customer_email=email,
                customer_contact=contact,
                notify_customer=False,
            )
        except Exception as exc:
            print(f"{index:<4} {amount:<12} {transaction_id:<22} FAILED ({type(exc).__name__})")
            time.sleep(2)
            continue

        url = link.get("short_url", "")
        created.append({"amount": amount, "transaction_id": transaction_id, "url": url})
        print(f"{index:<4} {amount:<12} {transaction_id:<22} {url}")
        time.sleep(1.5)

    over_1000 = [item for item in created if item["amount"] > 1000]
    print("\nDone.")
    print(f"Created {len(created)} links ({len(over_1000)} over INR 1,000).")
    print("\nNext steps:")
    print("1. Open each link and pay (success or fail) using Razorpay test cards.")
    print("2. Success card: 4111 1111 1111 1111")
    print("3. Decline card: 4000 0000 0000 0002")
    print("4. Check /audit-trail and /webhook-cases if your webhook server is running.")


if __name__ == "__main__":
    main()
