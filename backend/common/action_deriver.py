# DEPRECATED: legacy keyword-based action mapping.
# Replaced by producers + alert_engine in Increment 5.
from typing import Dict, List
from datetime import datetime

# ✅ Add Portfolio Logic
def derive_portfolio_actions(
    user_id: str,
    job_id: str,
    portfolio_report: str
):
    """
    Convert portfolio narrative + risk evaluation into alerts and todos.
    For now: deterministic mapping. Later: LLM-enhanced if desired.
    """

    alerts = []
    todos = []

    text = portfolio_report.lower() if portfolio_report else ""

    # ------ ALERT RULES ------
    if "concentration" in text:
        alerts.append({
            "clerk_user_id": user_id,
            "job_id": job_id,
            "symbol": None,
            "domain": "portfolio",
            "category": "concentration",
            "severity": "warning",
            "title": "Portfolio concentration detected",
            "message": "Your portfolio appears concentrated in a small number of assets or sectors.",
            "rationale": "Derived from portfolio analysis text."
        })

    if "volatility" in text or "risk" in text:
        alerts.append({
            "clerk_user_id": user_id,
            "job_id": job_id,
            "symbol": None,
            "domain": "portfolio",
            "category": "risk",
            "severity": "warning",
            "title": "Elevated investment risk highlighted",
            "message": "Your analysis indicates increased portfolio risk or instability.",
            "rationale": "Derived from analysis keywords."
        })


    # ------ TODO MAPPING ------
    if "rebalance" in text:
        todos.append({
            "clerk_user_id": user_id,
            "job_id": job_id,
            "symbol": None,
            "domain": "portfolio",
            "title": "Review portfolio rebalancing",
            "description": "Your portfolio analysis suggests rebalancing may be needed.",
            "rationale": "Action inferred from analysis content.",
            "action_type": "review",
            "priority": "medium",
            "due_at": None
        })


    return alerts, todos

# ✅ Add Retirement Companion Logic
def derive_retirement_actions(
    user_id: str,
    job_id: str,
    retirement_report: str
):

    alerts = []
    todos = []

    text = retirement_report.lower() if retirement_report else ""

    # ------ ALERT RULES ------
    if "probability" in text or "success rate" in text:
        alerts.append({
            "clerk_user_id": user_id,
            "job_id": job_id,
            "symbol": None,
            "domain": "retirement",
            "category": "probability",
            "severity": "critical",
            "title": "Retirement plan at risk",
            "message": f"Success probability might be low - refer retirement analysis.",
            "rationale": "Current savings and asset model show elevated failure risk."
        })

    if "success" in text and "%" in text:
        alerts.append({
            "clerk_user_id": user_id,
            "job_id": job_id,
            "symbol": None,
            "domain": "retirement",
            "category": "probability",
            "severity": "critical",
            "title": "Retirement plan at risk",
            "message": f"Check Success rate in retirement analysis.",
            "rationale": "Current savings and asset model show elevated failure risk."
        })

    if "gap" in text or "shortfall" in text:
        alerts.append({
            "clerk_user_id": user_id,
            "job_id": job_id,
            "symbol": None,
            "domain": "retirement",
            "category": "income",
            "severity": "warning",
            "title": "Retirement income gap detected",
            "message": f"Estimated annual shortfall - refer retirement analysis.",
            "rationale": "Projected income does not meet target."
        })

    # ------ TODO MAPPING ------
    if "increase savings" in text:
        todos.append({
            "clerk_user_id": user_id,
            "job_id": job_id,
            "symbol": None,
            "domain": "retirement",
            "title": "Retirement savings gap detected",
            "description": "Your retirement analysis suggests shortfall in savings",
            "rationale": "Action inferred from analysis content.",
            "action_type": "review",
            "priority": "medium",
            "due_at": None
        })

    if "insurance" in text:
        todos.append({
            "clerk_user_id": user_id,
            "job_id": job_id,
            "symbol": None,
            "domain": "retirement",
            "title": "Potential Insurance gap detected",
            "description": "Your retirement analysis suggests under insured",
            "rationale": "Action inferred from analysis content.",
            "action_type": "review",
            "priority": "medium",
            "due_at": None
        })

    return alerts, todos
