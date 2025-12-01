import json
import os
import urllib.request
from common.job_tracker import JobTracker

# APP_RUNNER_URL = os.environ["APP_RUNNER_URL"].replace("https://", "")
app_runner_url = os.environ.get('APP_RUNNER_URL')
if not app_runner_url:
    raise ValueError("APP_RUNNER_URL environment variable not set")
    
# Remove any protocol if included
if app_runner_url.startswith('https://'):
    app_runner_url = app_runner_url.replace('https://', '')
elif app_runner_url.startswith('http://'):
    app_runner_url = app_runner_url.replace('http://', '')

def call_researcher(job_id, user_id, symbol):
    
    url = f"https://{app_runner_url}/research/symbol"
    payload = {
        "job_id": job_id,
        "user_id": user_id,
        "symbol": symbol,
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json"
    }
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers=headers
    )
    
    print("WORKER calling Researcher URL:", url)
    print("Headers:", headers)
    print("Body:", payload)

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
