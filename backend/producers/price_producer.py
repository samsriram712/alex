from datetime import datetime, timezone
from common.alert_engine import AlertContext
from common.alert_service import emit_alert


def on_price_update(symbol: str, pct_change: float, clerk_user_id: str):
    ctx = AlertContext(
        alert_id=None,
        clerk_user_id=clerk_user_id,
        domain="portfolio",
        category="price",
        severity="info",
        title=f"{symbol} moved {pct_change:.1f}%",
        message=f"{symbol} changed {pct_change:.1f}% today.",
        symbol=symbol,
        price_change_pct=pct_change,
        created_at=datetime.now(timezone.utc)
    )

    emit_alert(ctx)
