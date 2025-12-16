# backend/common/alert_engine.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass
class AlertContext:
    """
    Normalized view of an alert that the decision engine can reason on.
    This is intentionally independent of any ORM / DB model.

    Required (from alerts table):
      - clerk_user_id
      - job_id
      - domain
      - category
      - severity
      - title
      - message
      - symbol (optional in DB but very useful here)

    Optional metrics:
      - price_change_pct: today's % change (e.g. -8.3)
      - portfolio_drawdown_pct: portfolio % drawdown over some window
      - position_allocation_pct: % of portfolio in this symbol
      - earnings_surprise_pct: EPS surprise (%)
      - guidance_change: "raised" | "lowered" | "unchanged"
      - research_age_days: days since last research on this symbol
    """

    alert_id: Optional[str]  # UUID as string or None before insert
    clerk_user_id: str
    job_id: Optional[str] 
    domain: str  # 'portfolio' | 'retirement'
    category: str  # 'price', 'risk', 'earnings', 'research_gap', etc.
    severity: str  # 'info', 'warning', 'critical'
    title: str
    message: str
    symbol: Optional[str] = None
    rationale: Optional[str] = None

    # Optional metrics (may be None if not applicable)
    price_change_pct: Optional[float] = None
    portfolio_drawdown_pct: Optional[float] = None
    position_allocation_pct: Optional[float] = None
    earnings_surprise_pct: Optional[float] = None
    guidance_change: Optional[str] = None  # 'raised' | 'lowered' | 'unchanged'
    research_age_days: Optional[int] = None

    created_at: Optional[datetime] = None


@dataclass
class TodoSpec:
    """
    Specification for a new todo row. The caller is responsible for:
      - assigning todo_id (DB default)
      - setting job_id if applicable
      - applying due_at or overriding fields as needed
      - avoiding duplicates (same symbol+action_type in open/in_progress)
    """
    clerk_user_id: str
    job_id: Optional[str] 
    domain: str
    title: str
    description: str
    action_type: str  # matches todos.action_type
    priority: str  # 'low' | 'medium' | 'high'
    symbol: Optional[str] = None
    rationale: Optional[str] = None
    due_at: Optional[datetime] = None
    source_alert_id: Optional[str] = None  # FK to alerts.alert_id


@dataclass
class EngineResult:
    """
    Output of the decision engine.

    alert_updates:
      columns to update in 'alerts' row (partial).
      Example:
        {
          "severity": "critical",
          "action_required": True,
          "confidence_score": 90,
          "action_hint": "review",
          "rationale": "Large price drop detected"
        }

    todo_spec:
      specification for a NEW todo that should be created.
      The caller may decide NOT to create it (e.g. deduped).
    """
    alert_updates: Dict[str, Any]
    todo_spec: Optional[TodoSpec]


# ---------------------------------------------------------------------------
# Rule abstraction
# ---------------------------------------------------------------------------

ConditionFn = Callable[[AlertContext], bool]
ApplyFn = Callable[[AlertContext], EngineResult]


@dataclass
class Rule:
    name: str
    description: str
    condition: ConditionFn
    apply: ApplyFn


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _build_result(
    alert: AlertContext,
    *,
    severity: Optional[str] = None,
    action_required: bool,
    confidence_score: int,
    action_hint: str,
    rationale: str,
    create_todo: bool = False,
    todo_action_type: Optional[str] = None,
    todo_priority: Optional[str] = None,
    todo_due_in_days: Optional[int] = None,
) -> EngineResult:
    """Utility to standardize EngineResult construction."""
    # Ensure reasonable bounds
    confidence_score = max(0, min(100, confidence_score))

    alert_updates: Dict[str, Any] = {
        "action_required": action_required,
        "confidence_score": confidence_score,
        "action_hint": action_hint,
        "rationale": rationale,
    }
    if severity is not None:
        alert_updates["severity"] = severity

    todo_spec: Optional[TodoSpec] = None
    if create_todo and todo_action_type and todo_priority:
        due_at: Optional[datetime] = None
        if todo_due_in_days is not None and alert.created_at:
            due_at = alert.created_at + timedelta(days=todo_due_in_days)

        todo_spec = TodoSpec(
            clerk_user_id=alert.clerk_user_id,
            job_id=alert.job_id,
            domain=alert.domain,
            title=_default_todo_title(alert, action_hint),
            description=alert.message,
            action_type=todo_action_type,
            priority=todo_priority,
            symbol=alert.symbol,
            rationale=rationale,
            due_at=due_at,
            source_alert_id=alert.alert_id,
        )

    return EngineResult(alert_updates=alert_updates, todo_spec=todo_spec)


def _default_todo_title(alert: AlertContext, action_hint: str) -> str:
    """Generate a reasonable default todo title from the alert and action."""
    action_verb = {
        "review": "Review",
        "rebalance": "Rebalance",
        "investigate": "Investigate",
        "monitor": "Monitor",
        "ignore": "Review"  # if we still create a todo, 'ignore' is odd
    }.get(action_hint, "Review")

    if alert.symbol:
        return f"{action_verb} {alert.symbol} position"
    return f"{action_verb} alert: {alert.title}"


# ---------------------------------------------------------------------------
# Concrete rules (V1)
# ---------------------------------------------------------------------------

def _price_large_drop_condition(alert: AlertContext) -> bool:
    return (
        alert.category == "price"
        and alert.price_change_pct is not None
        and alert.price_change_pct <= -8.0
    )


def _price_large_drop_apply(alert: AlertContext) -> EngineResult:
    return _build_result(
        alert,
        severity="critical",
        action_required=True,
        confidence_score=90,
        action_hint="review",
        rationale=f"Price dropped {alert.price_change_pct:.1f}% in a single session.",
        create_todo=True,
        todo_action_type="review_position",
        todo_priority="high",
        todo_due_in_days=2,
    )


def _price_medium_drop_condition(alert: AlertContext) -> bool:
    return (
        alert.category == "price"
        and alert.price_change_pct is not None
        and -8.0 < alert.price_change_pct <= -4.0
    )


def _price_medium_drop_apply(alert: AlertContext) -> EngineResult:
    return _build_result(
        alert,
        severity="warning",
        action_required=True,
        confidence_score=80,
        action_hint="monitor",
        rationale=f"Price dropped {alert.price_change_pct:.1f}%. Worth monitoring.",
        create_todo=True,
        todo_action_type="monitor_trend",
        todo_priority="medium",
        todo_due_in_days=5,
    )


def _price_spike_condition(alert: AlertContext) -> bool:
    return (
        alert.category == "price"
        and alert.price_change_pct is not None
        and alert.price_change_pct >= 7.0
    )


def _price_spike_apply(alert: AlertContext) -> EngineResult:
    return _build_result(
        alert,
        severity="warning",
        action_required=False,  # informational for now
        confidence_score=75,
        action_hint="monitor",
        rationale=f"Price increased {alert.price_change_pct:.1f}%. Consider monitoring momentum.",
        create_todo=False,
    )


def _portfolio_drawdown_condition(alert: AlertContext) -> bool:
    return (
        alert.category == "risk"
        and alert.portfolio_drawdown_pct is not None
        and alert.portfolio_drawdown_pct <= -12.0
    )


def _portfolio_drawdown_apply(alert: AlertContext) -> EngineResult:
    return _build_result(
        alert,
        severity="critical",
        action_required=True,
        confidence_score=90,
        action_hint="rebalance",
        rationale=f"Portfolio drawdown of {alert.portfolio_drawdown_pct:.1f}% exceeds threshold.",
        create_todo=True,
        todo_action_type="rebalance_portfolio",
        todo_priority="high",
        todo_due_in_days=3,
    )


def _overweight_position_condition(alert: AlertContext) -> bool:
    return (
        alert.category == "risk"
        and alert.position_allocation_pct is not None
        and alert.position_allocation_pct >= 35.0
    )


def _overweight_position_apply(alert: AlertContext) -> EngineResult:
    return _build_result(
        alert,
        severity="warning",
        action_required=True,
        confidence_score=85,
        action_hint="rebalance",
        rationale=f"Position allocation at {alert.position_allocation_pct:.1f}% exceeds target.",
        create_todo=True,
        todo_action_type="rebalance_portfolio",
        todo_priority="medium",
        todo_due_in_days=7,
    )


def _earnings_miss_condition(alert: AlertContext) -> bool:
    return (
        alert.category == "earnings"
        and (
            (alert.earnings_surprise_pct is not None and alert.earnings_surprise_pct < 0)
            or alert.guidance_change == "lowered"
        )
    )


def _earnings_miss_apply(alert: AlertContext) -> EngineResult:
    surprise_str = ""
    if alert.earnings_surprise_pct is not None:
        surprise_str = f"Earnings surprise {alert.earnings_surprise_pct:.1f}% below expectations. "
    guidance_str = ""
    if alert.guidance_change == "lowered":
        guidance_str = "Guidance lowered. "

    rationale = (surprise_str + guidance_str).strip() or "Negative earnings event."

    return _build_result(
        alert,
        severity="critical",
        action_required=True,
        confidence_score=88,
        action_hint="review",
        rationale=rationale,
        create_todo=True,
        todo_action_type="review_position",
        todo_priority="high",
        todo_due_in_days=3,
    )


def _earnings_beat_condition(alert: AlertContext) -> bool:
    return (
        alert.category == "earnings"
        and alert.earnings_surprise_pct is not None
        and alert.earnings_surprise_pct >= 5.0
        and alert.guidance_change in (None, "raised", "unchanged")
    )


def _earnings_beat_apply(alert: AlertContext) -> EngineResult:
    guidance_str = ""
    if alert.guidance_change == "raised":
        guidance_str = " Guidance raised."

    rationale = (
        f"Earnings surprise {alert.earnings_surprise_pct:.1f}% above expectations."
        + guidance_str
    ).strip()

    return _build_result(
        alert,
        severity="info",
        action_required=False,
        confidence_score=80,
        action_hint="monitor",
        rationale=rationale,
        create_todo=False,
    )


def _research_gap_condition(alert: AlertContext) -> bool:
    return (
        alert.category == "research_gap"
        and alert.research_age_days is not None
        and alert.research_age_days >= 30
    )


def _research_gap_apply(alert: AlertContext) -> EngineResult:
    return _build_result(
        alert,
        severity="warning",
        action_required=True,
        confidence_score=70,
        action_hint="investigate",
        rationale=f"Last research on this symbol is {alert.research_age_days} days old.",
        create_todo=True,
        todo_action_type="research_symbol",
        todo_priority="medium",
        todo_due_in_days=7,
    )

# ADD RULES – Retirement income gap

def _retirement_income_gap_condition(alert: AlertContext) -> bool:
    return (
        alert.domain == "retirement"
        and alert.category == "income"
    )

def _retirement_income_gap_apply(alert: AlertContext) -> EngineResult:
    return _build_result(
        alert,
        severity="critical",
        action_required=True,
        confidence_score=90,
        action_hint="increase_contributions",
        rationale="Projected retirement income shortfall detected.",
        create_todo=True,
        todo_action_type="increase_contributions",
        todo_priority="high",
        todo_due_in_days=30,
    )

# ADD RULES – Retirement probability risk

def _retirement_probability_condition(alert: AlertContext) -> bool:
    return (
        alert.domain == "retirement"
        and "probability" in (alert.message or "").lower()
    )

def _retirement_probability_apply(alert: AlertContext) -> EngineResult:
    return _build_result(
        alert,
        severity="warning",
        action_required=True,
        confidence_score=85,
        action_hint="review_plan",
        rationale="Low retirement success probability detected.",
        create_todo=True,
        todo_action_type="review_retirement_plan",
        todo_priority="medium",
        todo_due_in_days=14,
    )


# ---------------------------------------------------------------------------
# Rule registry and engine
# ---------------------------------------------------------------------------

RULES: List[Rule] = [
    Rule(
        name="price_large_drop",
        description="Critical alert for large single-day price drop",
        condition=_price_large_drop_condition,
        apply=_price_large_drop_apply,
    ),
    Rule(
        name="price_medium_drop",
        description="Warning alert for moderate price drop",
        condition=_price_medium_drop_condition,
        apply=_price_medium_drop_apply,
    ),
    Rule(
        name="price_spike",
        description="Informational alert for large price gain",
        condition=_price_spike_condition,
        apply=_price_spike_apply,
    ),
    Rule(
        name="portfolio_drawdown",
        description="Critical portfolio-level drawdown",
        condition=_portfolio_drawdown_condition,
        apply=_portfolio_drawdown_apply,
    ),
    Rule(
        name="overweight_position",
        description="Position allocation above threshold",
        condition=_overweight_position_condition,
        apply=_overweight_position_apply,
    ),
    Rule(
        name="earnings_miss",
        description="Negative earnings surprise or lowered guidance",
        condition=_earnings_miss_condition,
        apply=_earnings_miss_apply,
    ),
    Rule(
        name="earnings_beat",
        description="Positive earnings surprise",
        condition=_earnings_beat_condition,
        apply=_earnings_beat_apply,
    ),
    Rule(
        name="research_gap",
        description="Research is stale and needs refresh",
        condition=_research_gap_condition,
        apply=_research_gap_apply,
    ),
    Rule(
        name="retirement_income_gap",
        description="Income shortfall in retirement projection",
        condition=_retirement_income_gap_condition,
        apply=_retirement_income_gap_apply,
    ),
    Rule(
        name="retirement_probability",
        description="Low retirement success probability",
        condition=_retirement_probability_condition,
        apply=_retirement_probability_apply,
    ),

]


class AlertDecisionEngine:
    """
    Main entry point.
    You can keep this completely framework-agnostic and call it from
    Lambdas, FastAPI routes, or background jobs.
    """

    def __init__(self, rules: Optional[List[Rule]] = None):
        self._rules = rules or RULES

    def evaluate(self, alert: AlertContext) -> EngineResult:
        """
        Apply rules in order and return the first matching result.
        If no rule matches, return a neutral default.
        """
        for rule in self._rules:
            if rule.condition(alert):
                return rule.apply(alert)

        # Default behaviour: informational, no todo
        return EngineResult(
            alert_updates={
                "action_required": False,
                "confidence_score": 50,
                "action_hint": "monitor",
                "rationale": alert.rationale
                or "No specific decision rule matched this alert.",
            },
            todo_spec=None,
        )
