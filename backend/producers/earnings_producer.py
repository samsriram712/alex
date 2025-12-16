from datetime import datetime, timezone
from common.alert_engine import AlertContext
from common.alert_service import emit_alert


def emit_earnings_event(
    clerk_user_id: str,
    job_id: str,
    symbol: str,
    eps_actual: float | None,
    eps_expected: float | None,
    guidance_change: str | None = None  # "raised" | "lowered" | None
):
    """
    Earnings producer.
    Does NOT decide severity or create todos.
    It only emits raw structured events.
    """

    earnings_surprise = None

    if eps_actual is not None and eps_expected not in (None, 0):
        earnings_surprise = ((eps_actual - eps_expected) / eps_expected) * 100

    title = f"Earnings update for {symbol}"
    message_parts = []

    if earnings_surprise is not None:
        message_parts.append(f"EPS surprise: {earnings_surprise:.1f}%")
    if guidance_change:
        message_parts.append(f"Guidance {guidance_change}")

    message = " | ".join(message_parts) or "Earnings update detected."

    ctx = AlertContext(
        alert_id=None,
        clerk_user_id=clerk_user_id,
        job_id=job_id,
        domain="portfolio",
        category="earnings",
        severity="info",
        title=title,
        message=message,
        symbol=symbol,
        earnings_surprise_pct=earnings_surprise,
        guidance_change=guidance_change,
        created_at=datetime.now(timezone.utc)
    )

    emit_alert(ctx)
