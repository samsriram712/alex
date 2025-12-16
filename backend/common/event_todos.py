from __future__ import annotations

from typing import Dict
from datetime import datetime, timezone
import logging

from common.todo_store import TodoStore
from common.alert_engine import TodoSpec
from common.events import DetectedEvent

logger = logging.getLogger(__name__)

# ============================
# Event → Todo Policy Mapping
# ============================

EVENT_TODO_MAP: Dict[str, Dict] = {
    "retirement_shortfall": {
        "title": "Review retirement plan",
        "description": "Your projected retirement income may be below target. Review assumptions and contribution levels.",
        "action_type": "review_retirement_plan",
        "priority": "high",
        "domain": "retirement",
    },
    "concentration_risk": {
        "title": "Review portfolio concentration",
        "description": "Your portfolio may be too concentrated in a small number of assets.",
        "action_type": "rebalance_portfolio",
        "priority": "high",
        "domain": "portfolio",
    },
    "rebalance_recommended": {
        "title": "Rebalance portfolio",
        "description": "Portfolio allocation may be drifting from target weights.",
        "action_type": "rebalance_portfolio",
        "priority": "medium",
        "domain": "portfolio",
    },
    "elevated_volatility": {
        "title": "Assess portfolio risk",
        "description": "Volatility is elevated. Review risk exposure.",
        "action_type": "review_risk_profile",
        "priority": "medium",
        "domain": "portfolio",
    },
}


# ============================
# Todo Automation
# ============================

EVENT_TYPE_ALIASES = {
    "income_gap": "retirement_shortfall",
    "income": "retirement_shortfall",
    "retirement_risk": "retirement_shortfall",
    "savings": "retirement_shortfall",
    "insurance": "retirement_shortfall",
    "risk": "concentration_risk",
}


def maybe_create_todo_from_event(event: DetectedEvent):
    """
    Turn a DetectedEvent into a Todo using policy mapping.
    Deduplicates on (user, symbol, open/in_progress).
    """

    # mapping = EVENT_TODO_MAP.get(event.event_type)
    canonical = EVENT_TYPE_ALIASES.get(event.event_type, event.event_type)
    mapping = EVENT_TODO_MAP.get(canonical)
    logger.info(f"[TodoMapper] event={event.event_type}, canonical={canonical}")

    if not mapping:
        return  # no automation rule

    if not event.user_id:
        return  # safety: no user

    store = TodoStore()

    # ✅ de-dup: do not create another open todo for same user+symbol
    existing = store.list_open_for_user_and_symbol(
        clerk_user_id=event.user_id,
        job_id=event.job_id,
        symbol=None,  # Event-level action (not per symbol)
    )

    if existing:
        return  # ✅ already has open todo for this type of issue

    # ✅ build TodoSpec (uses your real model)
    todo = TodoSpec(
        clerk_user_id=event.user_id,
        job_id=event.job_id,
        domain=mapping["domain"],
        title=mapping["title"],
        description=mapping["description"],
        action_type=mapping["action_type"],
        priority=mapping["priority"],
        symbol=None,
        rationale=f"Generated from event '{event.event_type}'",
        due_at=None,
        source_alert_id=None,  # we can add later once alert_id is returned
    )

    store.insert_todo(todo.__dict__)
