from job_tracker import JobTracker
from src import Database
import uuid


def test_job_tracker():
    db = Database()
    tracker = JobTracker()

    # Simulate an existing jobs.id from your jobs table
    job_id = str(uuid.uuid4())

    # Insert into existing jobs table manually for testing
    db.query_raw(
        """
        INSERT INTO jobs (id, clerk_user_id, job_type)
        VALUES (:id, :user, :jobtype)
        """,
        [{"name": "id", "value": {"stringValue": job_id}, "typeHint": "UUID"},
         {"name": "user", "value": {"stringValue": "test_user_001"}},
         {"name": "jobtype", "value": {"stringValue": "portfolio_analysis"}}],
    )

    symbols = ["AAPL", "MSFT", "TSLA"]
    account_id='8396d2f4-abef-4c79-854c-5795c8d44fe0'

    # Init tracker rows
    tracker.init_tracker_for_job(job_id, account_id=account_id, symbols=symbols)

    # Verify inserts
    status = tracker.get_job_status(job_id)
    assert status["symbol_count"] == 3
    assert len(status["items"]) == 3

    # Update symbol statuses
    tracker.mark_symbol_running(job_id, "AAPL")
    tracker.mark_symbol_done(job_id, "AAPL")

    status = tracker.get_job_status(job_id)
    aapl = next(i for i in status["items"] if i["symbol"] == "AAPL")
    assert aapl["status"] == "done"

    # Complete remaining symbols
    tracker.mark_symbol_done(job_id, "MSFT")
    tracker.mark_symbol_done(job_id, "TSLA")

    assert tracker.is_job_complete(job_id) is True

    print("JobTracker test completed successfully.")

if __name__ == "__main__":
    test_job_tracker()
