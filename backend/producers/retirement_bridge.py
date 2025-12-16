from datetime import datetime, timezone
from common.alert_engine import AlertContext
from common.alert_service import emit_alert

# from common.event_agent import detect_events_from_narrative
from common.event_agent import detect_events_via_llm as detect_events
from common.events import DetectedEvent
from common.event_todos import maybe_create_todo_from_event
from common.event_utils import map_event_severity_to_alert



import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


async def emit_retirement_facts(user_id: str, job_id: str, retirement_report: str):
    """
    Structured Retirement signal emitter.
    Replaces derive_retirement_actions + AlertStore/TodoStore direct inserts.
    """

    text = retirement_report.lower() if retirement_report else ""

    # ✅ Success probability risk
    if "success rate" in text or "probability" in text:
        ctx = AlertContext(
            alert_id=None,
            clerk_user_id=user_id,
            job_id=job_id,
            domain="retirement",
            category="risk",
            severity="warning",   # engine may upgrade
            title="Retirement plan risk detected",
            message="Success probability issue detected in retirement output.",
            rationale="Derived from retirement analysis.",
            created_at=datetime.now(timezone.utc)
        )
        emit_alert(ctx)
        logger.info(
        "Emitting retirement alert",
        extra={"user_id": user_id, "job_id": job_id, "keyword_hits": ["probability", "success rate"]}
        )


    # ✅ Income shortfall
    if "gap" in text or "shortfall" in text:
        ctx = AlertContext(
            alert_id=None,
            clerk_user_id=user_id,
            job_id=job_id,
            domain="retirement",
            category="income",
            severity="warning",
            title="Retirement income gap detected",
            message="User projected income below retirement goal.",
            rationale="Derived from retirement content.",
            created_at=datetime.now(timezone.utc)
        )
        emit_alert(ctx)
        logger.info(
        "Emitting retirement alert",
        extra={"user_id": user_id, "job_id": job_id, "keyword_hits": ["gap", "shortfall"]}
        )


    # ✅ Savings gap
    if "increase savings" in text:
        ctx = AlertContext(
            alert_id=None,
            clerk_user_id=user_id,
            job_id=job_id,
            domain="retirement",
            category="savings",
            severity="warning",
            title="Retirement contributions insufficient",
            message="Recommended increase in retirement contribution.",
            rationale="Derived from retirement model.",
            created_at=datetime.now(timezone.utc)
        )
        emit_alert(ctx)
        logger.info(
        "Emitting retirement alert",
        extra={"user_id": user_id, "job_id": job_id, "keyword_hits": ["savings", "shortfall"]}
        )


    # ✅ Insurance risk
    if "insurance" in text:
        ctx = AlertContext(
            alert_id=None,
            clerk_user_id=user_id,
            job_id=job_id,
            domain="retirement",
            category="insurance",
            severity="warning",
            title="Potential insurance gap",
            message="User may be underinsured.",
            rationale="Derived from retirement model.",
            created_at=datetime.now(timezone.utc)
        )
        emit_alert(ctx)
        logger.info(
        "Emitting retirement alert",
        extra={"user_id": user_id, "job_id": job_id, "keyword_hits": ["insurance", "underinsured"]}
        )

        # === Event Intelligence Layer (Option C) ===
    events = await detect_events(
        user_id=user_id,
        job_id=job_id,
        source="retirement",
        narrative=retirement_report,
    )

    for event in events:
        ctx = AlertContext(
            alert_id=None,
            clerk_user_id=user_id,
            job_id=job_id,
            domain="retirement",
            category=event.event_type,
            severity=map_event_severity_to_alert(event.severity),
            title=event.title,
            message=event.explanation,
            created_at=datetime.now(timezone.utc),
        )
        emit_alert(ctx)
        logger.info(
            "Emitting retirement event-derived alert",
            extra={
                "user_id": user_id,
                "job_id": job_id,
                "event_type": event.event_type,
                "severity": event.severity,
            },
        )

    for event in events:
        maybe_create_todo_from_event(event)

