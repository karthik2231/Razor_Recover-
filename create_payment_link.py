import os
import uuid
from dotenv import load_dotenv
import razorpay


load_dotenv()


# ---------------------------------------------------------------------------
# Lazy Razorpay client
#
# The original code created the client at module import time, which meant
# os.getenv() was called before .env was reliably loaded in some import
# orders (e.g. tests). The client is now created on first use.
# ---------------------------------------------------------------------------

def _get_razorpay_client():
    """Return a Razorpay client configured from current environment variables."""
    
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")

    if not key_id or not key_secret:
        raise RuntimeError(
            "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in the "
            "root .env file before creating a Razorpay client."
        )

    return razorpay.Client(auth=(key_id, key_secret))


def create_test_payment_link(
    amount,
    customer_name="Test Customer",
    customer_email="test@example.com",
    customer_contact="8610169138",
):
    transaction_id = f"TXN_TEST_{uuid.uuid4().hex[:8]}"
    client = _get_razorpay_client()

    # pyrefly: ignore [missing-attribute]
    payment_link = client.payment_link.create(
        {
            "amount": int(round(float(amount) * 100)),
            "currency": "INR",
            "description": "RazorRecover Test Payment",
            "reference_id": transaction_id,
            "customer": {
                "name": customer_name,
                "email": customer_email,
                "contact": customer_contact,
            },
            "notify": {
                "sms": False,
                "email": False,
            },
            "reminder_enable": False,
        },
        timeout=10,
    )

    return transaction_id, payment_link


def create_recovery_payment_link(
    *,
    transaction_id: str,
    amount: float,
    customer_name: str,
    customer_email: str,
    customer_contact: str,
    notify_customer: bool = False,
) -> dict:
    """Create a bounded Test Mode recovery link with the supplied reference."""
    client = _get_razorpay_client()

    # pyrefly: ignore [missing-attribute]
    payment_link = client.payment_link.create(
        {
            "amount": int(round(float(amount) * 100)),
            "currency": "INR",
            "description": "RazorRecover Recovery Payment",
            "reference_id": transaction_id,
            "customer": {
                "name": customer_name,
                "email": customer_email,
                "contact": customer_contact,
            },
            "notify": {"sms": notify_customer, "email": notify_customer},
            "reminder_enable": False,
        },
        timeout=10,
    )
    return payment_link


def fetch_test_payment_link(payment_link_id: str) -> dict:
    """Retrieve a previously created Razorpay Test Mode payment link."""
  
    return _get_razorpay_client().payment_link.fetch(payment_link_id)


def fetch_test_payment(payment_id: str) -> dict:
    """Retrieve a Test Mode payment associated with a payment link."""
    return _get_razorpay_client().payment.fetch(payment_id)


if __name__ == "__main__":
    amount = float(input("Enter payment amount in INR: ₹"))
    transaction_id, result = create_test_payment_link(amount=amount)
    print("\nNormal Test Payment Created!")
    print("Transaction ID:", transaction_id)
    print("Amount: ₹", amount)
    print("Payment Link:", result["short_url"])
