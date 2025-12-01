from __future__ import annotations
from typing import List, Dict, Optional

from database.src.models import Database   # ⬅️ Matches refresher codebase pattern


class JobTracker:
    """
    Uses the existing Database() abstraction,
    consistent with refresher and other backend modules.
    """

    def __init__(self) -> None:
        self.db = Database()

    # ---------------------------------------
    # Initialize tracker rows for a job (existing jobs.id)
    # ---------------------------------------
    def init_tracker_for_job(
        self,
        job_id: str,
        symbols: List[str],
    ) -> None:

        # Deduplicate symbols to keep counts consistent
        unique_symbols = sorted(set(symbols))
                       
        # Insert into job_tracker
        self.db.query_raw(
            """
            INSERT INTO job_tracker (job_id, symbol_count, symbols_done, status)
            VALUES (:job_id, :symbol_count, 0, 'pending')
            ON CONFLICT (job_id) DO NOTHING
            """,
            [
                {"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"},
                {"name": "symbol_count", "value": {"longValue": len(symbols)}},
            ]
        )

        # Insert job_tracker_items
        for sym in unique_symbols:
            self.db.query_raw(
                """
                INSERT INTO job_tracker_items (job_id, symbol, status)
                VALUES (:job_id, :symbol, 'pending')
                ON CONFLICT (job_id, symbol) DO NOTHING
                """,
                [
                    {"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"},
                    {"name": "symbol", "value": {"stringValue": sym}},
                ]
            )

    # ---------------------------------------
    # Status updates
    # ---------------------------------------
    def mark_symbol_running(self, job_id: str, symbol: str) -> None:
        self.db.query_raw(
            """
            UPDATE job_tracker_items
            SET status='running', last_updated=NOW()
            WHERE job_id=:job_id AND symbol=:symbol
            """,
            [
                {"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"},
                {"name": "symbol", "value": {"stringValue": symbol}},
            ]
        )

        self.db.query_raw(
            """
            UPDATE job_tracker
            SET status='running'
            WHERE job_id=:job_id AND status='pending'
            """,
            [{"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"}]
        )

    def mark_symbol_done(self, job_id: str, symbol: str) -> None:
        self.db.query_raw(
            """
            UPDATE job_tracker_items
            SET status='done', last_updated=NOW()
            WHERE job_id=:job_id AND symbol=:symbol 
            """,
            [
                {"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"},
                {"name": "symbol", "value": {"stringValue": symbol}},
            ]
        )

        self.db.query_raw(
            """
            UPDATE job_tracker
            SET symbols_done = symbols_done + 1
            WHERE job_id=:job_id
            """,
            [{"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"}]
        )

        # mark job done when all symbols done
        self.db.query_raw(
            """
            UPDATE job_tracker
            SET status='done', completed_at=NOW()
            WHERE job_id=:job_id AND symbols_done >= symbol_count
            """,
            [{"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"}]
        )

    def mark_symbol_error(self, job_id: str, symbol: str, error: str) -> None:
        self.db.query_raw(
            """
            UPDATE job_tracker_items
            SET status='error', error_message=:err, last_updated=NOW()
            WHERE job_id=:job_id AND symbol=:symbol
            """,
            [
                {"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"},
                {"name": "symbol", "value": {"stringValue": symbol}},
                {"name": "err", "value": {"stringValue": error[:1000]}},
            ]
        )

        self.db.query_raw(
            """
            UPDATE job_tracker
            SET status='error'
            WHERE job_id=:job_id AND status!='error'
            """,
            [{"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"}]
        )

    # ---------------------------------------
    # Reads
    # ---------------------------------------
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        rows = self.db.query_raw(
            """
            SELECT job_id, status, symbol_count, symbols_done,
                   created_at, completed_at
            FROM job_tracker
            WHERE job_id=:job_id
            """,
            [{"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"}]
        )

        if not rows:
            return None

        job = rows[0]

        items = self.db.query_raw(
            """
            SELECT symbol, status, retry_count, error_message, last_updated
            FROM job_tracker_items
            WHERE job_id=:job_id
            ORDER BY symbol
            """,
            [{"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"}]
        )

        job["items"] = items
        return job

    def is_job_complete(self, job_id: str) -> bool:
        row = self.db.query_raw(
            """
            SELECT symbol_count, symbols_done, status
            FROM job_tracker
            WHERE job_id=:job_id
            """,
            [{"name": "job_id", "value": {"stringValue": job_id}, "typeHint": "UUID"}]
        )

        if not row:
            return False

        r = row[0]
        return r["symbol_count"] >= r["symbols_done"] and r["status"] == "done"
