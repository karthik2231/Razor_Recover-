import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)

def create_demo_pdf(filename="RazorRecover_AI_Demo_Guide.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#1e293b")
    brand_blue = colors.HexColor("#2563eb")
    accent_green = colors.HexColor("#059669")
    dark_gray = colors.HexColor("#334155")
    bg_light = colors.HexColor("#f8fafc")
    border_color = colors.HexColor("#e2e8f0")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=primary_color,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=brand_blue,
        spaceAfter=15,
    )

    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=brand_blue,
        spaceBefore=12,
        spaceAfter=8,
    )

    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=primary_color,
        spaceBefore=8,
        spaceAfter=4,
    )

    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=dark_gray,
        spaceAfter=6,
    )

    script_spoken = ParagraphStyle(
        "ScriptSpoken",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4,
    )

    cue_style = ParagraphStyle(
        "ScreenCue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=12,
        textColor=accent_green,
        spaceAfter=4,
    )

    badge_style = ParagraphStyle(
        "BadgeText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )

    elements = []

    # Title Block
    elements.append(Paragraph("RazorRecover AI — Master Demo & Submission Guide", title_style))
    elements.append(Paragraph("Agentic AI-Powered Revenue Recovery for Razorpay • Complete Presentation & Submission Kit", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=brand_blue, spaceAfter=15))

    # SECTION 1: Form Answers
    elements.append(Paragraph("1. Form Submission Answers (Ready to Copy)", h1_style))
    elements.append(Paragraph("<b>Project Objectives (What does it solve?)</b>", h2_style))
    
    obj_text = (
        "Failed digital payments (bank timeouts, UPI drops, card glitches) cause massive revenue leakage and "
        "cart abandonment for merchants. Traditional recovery is manual and slow, while blind retries risk fraud.<br/><br/>"
        "<b>RazorRecover AI</b> solves this through safety-first, agentic revenue recovery for Razorpay:<br/>"
        "• <b>Real-Time Webhook Ingestion</b>: Intercepts Razorpay <code>payment.failed</code> events with HMAC-SHA256 verification and idempotency locks.<br/>"
        "• <b>AI Recommendation & Scoring</b>: Uses <b>Google Gemini (gemini-3.6-flash)</b> to analyze failure telemetry and calculate a 0–100 recovery score.<br/>"
        "• <b>Deterministic Policy Guardrails</b>: Enforces hard business rules (ALLOW, REVIEW, DENY) to eliminate financial AI hallucination.<br/>"
        "• <b>Dual Execution & Reconciliation</b>: Offers human reviewer oversight alongside bounded auto-recovery for micro-transactions (&lt;= ₹1,000), generating Razorpay payment links and auto-reconciling captured payments."
    )
    elements.append(Paragraph(obj_text, body_style))
    elements.append(Spacer(1, 6))

    elements.append(Paragraph("<b>Build Challenges & Technical Obstacles</b>", h2_style))
    challenges_text = (
        "1. <b>Financial Safety vs. AI Autonomy</b>: Unchecked LLM execution in finance causes high liability. We decoupled Gemini AI as strictly advisory and built an independent deterministic policy engine enforcing a 9-point checklist before any auto-execution.<br/>"
        "2. <b>Webhook Idempotency & Error Normalization</b>: Retried webhooks and fragmented gateway errors across UPI and cards cause duplicate charges. We built HMAC signature validation, database idempotency locks, and an error code taxonomy mapper.<br/>"
        "3. <b>Payment Gateway Lifecycle Simulation</b>: Testing failure-to-capture loops without real money was difficult due to gateway link timeouts. We built a developer simulation engine and Razorpay Test Mode integration for instant, zero-delay testing."
    )
    elements.append(Paragraph(challenges_text, body_style))
    elements.append(Spacer(1, 10))

    elements.append(HRFlowable(width="100%", thickness=0.5, color=border_color, spaceAfter=10))

    # SECTION 2: Master Speaking Script
    elements.append(Paragraph("2. Master 3.5-Minute Demo Video Script", h1_style))
    elements.append(Paragraph("Read these exact words while performing the screen actions during your recording:", body_style))
    elements.append(Spacer(1, 4))

    script_data = [
        ("Part 1: The Hook & Introduction (0:00 - 0:35)",
         "🖥️ Screen: Open React Dashboard homepage (http://localhost:5173)",
         "\"Hi everyone, I'm Karthik, and today I'm presenting RazorRecover AI. In online commerce, payment failures from bank timeouts and UPI drops cause millions in lost revenue every day. When a payment fails, over 70% of customers abandon their cart and never return. RazorRecover AI uses Google Gemini AI to analyze failed Razorpay payments and safely recover lost sales with strict safety guardrails. Let's see it in action!\""),
        
        ("Part 2: Failure Simulation & AI Scoring (0:35 - 1:30)",
         "🖥️ Screen: Go to 'Developer Test' tab -> Amount: ₹950, Reason: bank_timeout -> Click 'Simulate Failure' -> Go to 'Webhook Cases' -> Open Case",
         "\"When a payment fails on Razorpay, our backend securely captures the webhook with HMAC-SHA256 signature verification and idempotency locks. The transaction enters our intelligence pipeline: first, our custom scoring algorithm evaluates the failure telemetry to assign a 0 to 100 Recovery Score. Next, Google Gemini (gemini-3.6-flash) analyzes the failure pattern, assigns an AI confidence score, and flags any potential risks. A built-in rule fallback ensures zero downtime if the AI API is ever unreachable.\""),
        
        ("Part 3: Safety Guardrails & Human Approval (1:30 - 2:20)",
         "🖥️ Screen: Scroll down to Policy Engine decision -> Click 'Approve' button -> Show generated Razorpay Payment Link",
         "\"Because financial actions cannot be left to unchecked AI, our Deterministic Policy Engine enforces strict rules: ALLOW, REVIEW, or DENY. Low-risk micro-transactions under ₹1,000 with 90%+ AI confidence can auto-execute, while larger amounts are safely held for Human Review. The reviewer inspects Gemini's advice and clicks Approve. Instantly, our system calls Razorpay's API in Test Mode to generate an active recovery link for the customer.\""),

        ("Part 4: Live Payment & Automated Settlement (2:20 - 3:00)",
         "🖥️ Screen: Click link -> Pay with Card 4111 1111 1111 1111, click 'Success' -> Return to Dashboard -> Show PAYMENT_CAPTURED & Audit Log",
         "\"Now, when the customer completes payment through this recovery link, Razorpay fires a payment.captured webhook. Our system automatically reconciles the transaction in real time, updates the lifecycle status to PAYMENT_CAPTURED, and marks the revenue as recovered! Every decision and state change is permanently logged in our append-only JSONL audit trail for complete compliance.\""),

        ("Part 5: System Architecture & Wrap-up (3:00 - 3:30)",
         "🖥️ Screen: Open Mermaid Diagram in README.md -> Return to Dashboard Overview",
         "\"To summarize our architecture: Webhooks ingest failures into our Gemini AI and scoring pipeline. A deterministic policy engine eliminates hallucination. Cases pass to human review or auto-execution, generating Razorpay links that auto-reconcile on capture. RazorRecover AI turns lost payments into recovered revenue safely and autonomously. Thank you so much!\"")
    ]

    for part_title, screen_cue, spoken_text in script_data:
        box_content = [
            [Paragraph(f"<b>{part_title}</b>", h2_style)],
            [Paragraph(f"<b>{screen_cue}</b>", cue_style)],
            [Paragraph(f"🗣️ <i>{spoken_text}</i>", script_spoken)],
        ]
        t = Table(box_content, colWidths=[530])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg_light),
            ('BOX', (0,0), (-1,-1), 1, border_color),
            ('PADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8))

    elements.append(PageBreak())

    # SECTION 3: System Architecture & Thresholds
    elements.append(Paragraph("3. System Architecture & Safety Thresholds", h1_style))
    
    thresh_data = [
        [Paragraph("<b>Threshold Tier</b>", h2_style), Paragraph("<b>Amount Limit</b>", h2_style), Paragraph("<b>Safety Rule Enforced</b>", h2_style)],
        [Paragraph("<b>Hard Policy Block</b>", body_style), Paragraph("<b>&gt; ₹10,000</b>", body_style), Paragraph("Completely BLOCKED (DENY). Enterprise fraud prevention.", body_style)],
        [Paragraph("<b>Execution Ceiling</b>", body_style), Paragraph("<b>&gt; ₹5,000</b>", body_style), Paragraph("Gateway adapter refuses link generation without config change.", body_style)],
        [Paragraph("<b>Human Review Gate</b>", body_style), Paragraph("<b>₹1,001 to ₹5,000</b>", body_style), Paragraph("AI auto-approval disabled. Operator must review & sign off.", body_style)],
        [Paragraph("<b>AI Auto-Recovery</b>", body_style), Paragraph("<b>&lt;= ₹1,000</b>", body_style), Paragraph("Auto-executes ONLY if 1st attempt, zero risk flags, &gt;=90% AI confidence.", body_style)],
    ]
    t_thresh = Table(thresh_data, colWidths=[120, 100, 310])
    t_thresh.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#e2e8f0")),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(t_thresh)
    elements.append(Spacer(1, 12))

    # SECTION 4: Dual Persistence Rationale
    elements.append(Paragraph("4. Storage Design: SQLite vs. JSONL", h1_style))
    db_text = (
        "• <b>SQLite (recovery_cases.db)</b>: Powers the live state machine. Used for active case state transitions "
        "(PENDING_REVIEW &rarr; APPROVED &rarr; PAYMENT_CAPTURED), real-time frontend filtering, and DB-level idempotency locks.<br/>"
        "• <b>JSONL (data/audit_log.jsonl)</b>: Append-only immutable log. Never updates or deletes rows. Provides a tamper-evident "
        "chronological timeline of every AI score, policy check, reviewer token, and gateway response for FinTech compliance."
    )
    elements.append(Paragraph(db_text, body_style))
    elements.append(Spacer(1, 10))

    # SECTION 5: Judge Q&A Cheat Sheet
    elements.append(Paragraph("5. Judge / Evaluator Q&A Cheat Sheet", h1_style))
    qa_data = [
        ("Q: Why not let AI auto-recover every transaction?",
         "A: Financial liability and chargeback risks. High-value transactions or ambiguous errors require human oversight. We enforce a 9-point rule checklist so only low-risk, high-confidence micro-transactions (< ₹1,000) can auto-execute."),
        ("Q: What if the Google Gemini API is down or slow?",
         "A: We built an automatic rule-based fallback engine (decision_service.py). If Gemini is unreachable, rule scoring activates seamlessly with zero transaction downtime."),
        ("Q: How does it prevent duplicate charges or recovery links?",
         "A: We use cryptographic HMAC-SHA256 signature validation and SQLite primary key idempotency locks on event IDs and reference IDs."),
    ]
    for q, a in qa_data:
        elements.append(Paragraph(f"<b>{q}</b>", h2_style))
        elements.append(Paragraph(f"<i>{a}</i>", body_style))
        elements.append(Spacer(1, 4))

    doc.build(elements)
    print(f"PDF generated successfully at {filename}")

if __name__ == "__main__":
    create_demo_pdf()
