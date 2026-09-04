def calculate_recovery_score(transaction):
    score = 0
    factors = []

    # 1. Failure reason score
    failure_scores = {
        "bank_timeout": 30,
        "network_error": 30,
        "upi_failure": 25,
        "authentication_failed": 20,
        "card_declined": 15,
        "insufficient_funds": 10,
        "payment_failed": 10,
    }

    failure_reason = transaction.get("failure_reason", "")

    reason_score = failure_scores.get(failure_reason, 0)
    score += reason_score

    factors.append(
        f"Failure reason: {failure_reason} (+{reason_score})"
    )

    # 2. Customer payment history
    successful_payments = int(
        transaction.get("successful_payments", 0)
    )

    if successful_payments >= 10:
        history_score = 25
    elif successful_payments >= 5:
        history_score = 15
    elif successful_payments >= 1:
        history_score = 5
    else:
        history_score = 0

    score += history_score

    factors.append(
        f"Successful payments: {successful_payments} (+{history_score})"
    )

    # 3. Previous recovery attempts
    attempts = int(
        transaction.get("previous_recovery_attempts", 0)
    )

    if attempts == 0:
        attempts_score = 20
    elif attempts == 1:
        attempts_score = 10
    else:
        attempts_score = 0

    score += attempts_score

    factors.append(
        f"Previous recovery attempts: {attempts} (+{attempts_score})"
    )

    # 4. Transaction amount
    amount = float(transaction.get("amount", 0))

    if amount >= 5000:
        amount_score = 15
    elif amount >= 2000:
        amount_score = 10
    else:
        amount_score = 5

    score += amount_score

    factors.append(
        f"Transaction amount: ₹{amount:,.0f} (+{amount_score})"
    )

    # Ensure score does not exceed 100
    score = min(score, 100)

    # Classify opportunity
    if score >= 70:
        opportunity = "HIGH"
    elif score >= 40:
        opportunity = "MEDIUM"
    else:
        opportunity = "LOW"

    return {
        "recovery_score": score,
        "opportunity": opportunity,
        "factors": factors
    }