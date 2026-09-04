from backend.app.services.recovery_service import calculate_recovery_score
from pathlib import Path
import pandas as pd


# Project root:
# backend/app/services/transaction_service.py -> go up 4 levels
BASE_DIR = Path(__file__).resolve().parents[3]

DATA_FILE = BASE_DIR / "data" / "transactions.csv"


def load_transactions():
    """Load all transactions from the CSV file."""
    return pd.read_csv(DATA_FILE)


def get_all_transactions():
    """Return all transactions as a list of dictionaries."""
    df = load_transactions()
    return df.fillna("").to_dict(orient="records")


def get_failed_transactions():
    """Return only failed transactions."""
    df = load_transactions()

    failed_df = df[df["payment_status"] == "failed"]

    return failed_df.fillna("").to_dict(orient="records")


def get_revenue_at_risk():
    """Calculate total revenue from failed transactions."""
    df = load_transactions()

    failed_df = df[df["payment_status"] == "failed"]

    total_revenue_at_risk = float(failed_df["amount"].sum())

    return {
        "failed_transaction_count": int(len(failed_df)),
        "total_revenue_at_risk": total_revenue_at_risk
    }

def get_scored_failed_transactions():
    """Calculate recovery scores for all failed transactions."""
    failed_transactions = get_failed_transactions()

    scored_transactions = []

    for transaction in failed_transactions:
        recovery_result = calculate_recovery_score(transaction)

        transaction["recovery_score"] = recovery_result["recovery_score"]
        transaction["opportunity"] = recovery_result["opportunity"]
        transaction["scoring_factors"] = recovery_result["factors"]

        scored_transactions.append(transaction)

    return sorted(
        scored_transactions,
        key=lambda x: x["recovery_score"],
        reverse=True
    )


def get_high_recovery_opportunities():
    """Return only high recovery opportunity transactions."""
    scored_transactions = get_scored_failed_transactions()

    return [
        transaction
        for transaction in scored_transactions
        if transaction["opportunity"] == "HIGH"
    ]

def get_recovery_case_by_id(transaction_id: str):
    cases = get_scored_failed_transactions()

    for transaction in cases:
        if transaction["transaction_id"] == transaction_id:
            return transaction

    return None