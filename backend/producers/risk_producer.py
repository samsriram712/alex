from datetime import datetime, timezone
from common.alert_engine import AlertContext
from common.alert_service import emit_alert


def emit_portfolio_risk(clerk_user_id: str, job_id: str, drawdown: float, symbol: str = None, alloc: float = None):
    ctx = AlertContext(
        alert_id=None,
        clerk_user_id=clerk_user_id,
        job_id=job_id,
        domain="portfolio",
        category="risk",
        severity="warning",
        title="Portfolio risk detected",
        message="Risk threshold exceeded.",
        symbol=symbol,
        portfolio_drawdown_pct=drawdown,
        position_allocation_pct=alloc,
        created_at=datetime.now(timezone.utc)
    )

    emit_alert(ctx)
