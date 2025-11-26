import json
import os
import urllib.request
from common.job_tracker import JobTracker

APP_RUNNER_URL = os.environ["APP_RUNNER_URL"].replace("https://", "")


def call_researcher(job_id, user_id, symbol):
    url = f"https://{APP_RUNNER_URL}/research/symbol"
    payload = {
        "job_id": job_id,
        "user_id": user_id,
        "symbol": symbol,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read().decode("utf-8")


def handler(event, context):
    tracker = JobTracker()

    for record in event["Records"]:
        msg = json.loads(record["body"])

        job_id = msg["job_id"]
        user_id = msg["user_id"]
        symbol = msg["symbol"]

        # Mark running
        tracker.mark_symbol_running(job_id, symbol)

        try:
            call_researcher(job_id, user_id, symbol)
            tracker.mark_symbol_done(job_id, symbol)
        except Exception as e:
            tracker.mark_symbol_error(job_id, symbol, str(e))
            raise

    return {"status": "ok"}
