from datetime import datetime, timezone
from common.alert_engine import AlertContext
from common.alert_service import emit_alert


def emit_stale_research(symbol, days, clerk_user_id, job_id):
    ctx = AlertContext(
        alert_id=None,
        clerk_user_id=clerk_user_id,
        job_id=job_id,
        domain="portfolio",
        category="research_gap",
        severity="warning",
        title=f"Research stale for {symbol}",
        message=f"Last research update {days} days ago.",
        symbol=symbol,
        research_age_days=days,
        created_at=datetime.now(timezone.utc)
    )

    emit_alert(ctx)
