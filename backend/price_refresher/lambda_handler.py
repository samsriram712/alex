import os, asyncio, logging
from src import Database
#from planner.prices import get_share_price_polygon
from prices import get_share_price_polygon

logger = logging.getLogger()
logger.setLevel(logging.INFO)

async def refresh_prices():
    db = Database()
    rows = db.query_raw("SELECT symbol FROM instruments WHERE symbol IS NOT NULL")
    count, skipped, failures = 0, 0, []
    for r in rows:
        sym = r["symbol"]
        try:
            price = get_share_price_polygon(sym)

            if price is None:
                logger.warning(
                    f"{sym}: no market price available; retaining previous price"
                )
                skipped += 1
                continue


            db.query_raw(
                "UPDATE instruments SET current_price = :p WHERE symbol = :s",
                [
                    {"name": "p", "value": {"doubleValue": price}},
                    {"name": "s", "value": {"stringValue": sym}},
                ],
            )
            count += 1
        except Exception as e:
            failures.append(sym)
            logger.warning(f"{sym}: {e}")
    logger.info(f"Refreshed {count} symbols; failures={failures}; skipped={skipped}")
    return {"count": count, "failures": failures}

def lambda_handler(event, context):
    return asyncio.run(refresh_prices())
