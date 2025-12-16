from producers.risk_producer import emit_portfolio_risk
from producers.research_gap import emit_stale_research
from producers.earnings_producer import emit_earnings_event
from common.alert_engine import AlertContext
from common.alert_service import emit_alert
import logging
from datetime import datetime, timezone

# from common.event_agent import detect_events_from_narrative
from common.event_agent import detect_events_via_llm as detect_events
from common.events import DetectedEvent
from common.event_todos import maybe_create_todo_from_event
from common.event_utils import map_event_severity_to_alert


logger = logging.getLogger()
logger.setLevel(logging.INFO)


async def emit_reporter_facts(user_id, job_id, portfolio_report: str):
    """
    Converts the reporter narrative into structured signal events.
    This replaces action_deriver.py entirely.
    """

    text = portfolio_report.lower() if portfolio_report else ""

    # ✅ Risk detection
    if "volatility" in text or "risk" in text:
        emit_portfolio_risk(
            clerk_user_id=user_id,
            job_id=job_id,
            drawdown=None
        )
        logger.info(
        "Emitting portfolio alert",
        extra={"user_id": user_id, "job_id": job_id, "keyword_hits": ["volatility", "risk"]}
        )

    # ✅ Concentration
    if "concentration" in text:
        emit_portfolio_risk(
            clerk_user_id=user_id,
            job_id=job_id,
            drawdown=None,
            symbol=None,
            alloc=40.0  # placeholder until symbol attribution improves
        )
        logger.info(
        "Emitting portfolio alert",
        extra={"user_id": user_id, "job_id": job_id, "keyword_hits": ["concentration", "risk"]}
        )


    # ✅ Rebalance intent
    if "rebalance" in text:
        ctx = AlertContext(
            alert_id=None,
            clerk_user_id=user_id,
            job_id=job_id,
            domain="portfolio",
            category="risk",
            severity="warning",
            title="Portfolio rebalance suggested",
            message="Reporter indicated rebalance recommendation.",
            created_at=datetime.now(timezone.utc)
        )
        emit_alert(ctx)
        logger.info(
        "Emitting portfolio alert",
        extra={"user_id": user_id, "job_id": job_id, "keyword_hits": ["rebalance", "portfolio"]}
        )

    # ✅ Stale research (heuristic placeholder)
    if "outdated" in text or "stale" in text:
        emit_stale_research(
            symbol="UNKNOWN",
            days=45,
            clerk_user_id=user_id,
            job_id=job_id
        )
        logger.info(
        "Emitting portfolio alert",
        extra={"user_id": user_id, "job_id": job_id, "keyword_hits": ["outdated", "stale", "research"]}
        )

        # === Event Intelligence Layer (Option C) ===
    events = await detect_events(
        user_id=user_id,
        job_id=job_id,
        source="reporter",
        narrative=portfolio_report,
    )

    for event in events:
        # Map DetectedEvent → AlertContext
        ctx = AlertContext(
            alert_id=None,
            clerk_user_id=user_id,
            job_id=job_id,
            domain="portfolio",
            category=event.event_type,
            severity=map_event_severity_to_alert(event.severity),
            title=event.title,
            message=event.explanation,
            created_at=datetime.now(timezone.utc),
        )
        emit_alert(ctx)
        logger.info(
            "Emitting event-derived alert",
            extra={
                "user_id": user_id,
                "job_id": job_id,
                "event_type": event.event_type,
                "severity": event.severity,
            },
        )
    
    for event in events:
        maybe_create_todo_from_event(event)


