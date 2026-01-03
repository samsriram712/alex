from src.models import Database
from typing import List, Dict, Optional
from uuid import UUID


class AlertStore:

    def __init__(self):
        self.db = Database()

    def alert_exists(self, clerk_user_id, category, domain, severity, symbol) -> bool:
        sql = """
            SELECT 1
            FROM alerts
            WHERE clerk_user_id = :user
                AND category = :category
                AND domain = :domain
                AND (:symbol::varchar IS NULL OR symbol = :symbol::varchar)
                AND status != 'dismissed'
                LIMIT 1
        """

        params = [
            {"name": "user", "value": {"stringValue": str(clerk_user_id)}},
            {"name": "category", "value": {"stringValue": str(category)}},
            {"name": "domain", "value": {"stringValue": str(domain)}},
            ]

        if symbol is None:
            params.append({"name": "symbol", "value": {"isNull": True}})
        else:
            params.append({"name": "symbol", "value": {"stringValue": str(symbol)}})

        rows = self.db.query_raw(sql, params)
        return bool(rows)

    # -------------------------
    # INSERT
    # -------------------------
    def insert_alert(self, alert: dict):
        
        # ============================
        # Alert deduplication
        # ============================
        if self.alert_exists(
            clerk_user_id=alert["clerk_user_id"],
            category=alert["category"],
            domain=alert["domain"],
            severity=alert["severity"],
            symbol=alert.get("symbol"),
        ):
            print(
                f"[AlertStore] Deduped alert: "
                f"user={alert['clerk_user_id']} "
                f"type={alert['category']} "
                f"domain={alert['domain']} "
                f"symbol={alert['symbol']}"
            )
            return None

        sql = """
            INSERT INTO alerts (
                alert_id, clerk_user_id, job_id, symbol,
                domain, category, severity,
                title, message, rationale
            )
            VALUES (
                uuid_generate_v4(), :user, :job, :symbol,
                :domain, :category, :severity,
                :title, :message, :rationale
            )
            RETURNING alert_id
        """

        params = self._build_params(alert)

        # ✅ INJECT UUID WITH TYPE HINT
        if alert.get("job_id"):
            params.append({
                "name": "job",
                "value": {"stringValue": str(alert["job_id"])},
                "typeHint": "UUID"
            })
        else:
            params.append({
                "name": "job",
                "value": {"isNull": True}
            })

        rows = self.db.query_raw(sql, params)
        # Aurora Data API wrapper returns list[dict]
        return rows[0]["alert_id"] if rows else None


    def insert_bulk(self, alerts: List[Dict]) -> None:
        for alert in alerts:
            self.insert_alert(alert)

    # -------------------------
    # QUERY
    # -------------------------
    def list_alerts(self,
                    clerk_user_id: str,
                    symbol: Optional[str] = None,
                    domain: Optional[str] = None,
                    status: Optional[str] = None,
                    job_id: Optional[UUID] = None,
                    include_dismissed: bool = False,
                    limit: int = 50):

        sql = """
            SELECT *
            FROM alerts
            WHERE clerk_user_id = :user
                AND (:symbol::varchar IS NULL OR symbol = :symbol::varchar)
                AND (:domain::varchar IS NULL OR domain = :domain::varchar)
                AND (:include_dismissed::boolean = TRUE OR status != 'dismissed')
                AND (:status::varchar IS NULL OR status = :status::varchar)
                AND (:job_id::uuid IS NULL OR job_id = :job_id::uuid)
            ORDER BY created_at DESC
        """
        sql += f" LIMIT {int(limit)}"

        return self.db.query_raw(sql, self._query_params(
            user=clerk_user_id,
            symbol=symbol,
            domain=domain,
            status=status,
            job_id=job_id,
            include_dismissed=include_dismissed
            # limit=limit
        ))

    def summarize(self, clerk_user_id: str):
        sql = """
            SELECT
                domain,
                COUNT(*) FILTER (WHERE status='new') AS unread,
                COUNT(*) FILTER (WHERE severity='critical') AS critical
            FROM alerts
            WHERE clerk_user_id = :user
            GROUP BY domain
        """
        rows = self.db.query_raw(sql, [{"name":"user","value":{"stringValue":clerk_user_id}}])

        return {
            "unread_count": sum(r["unread"] for r in rows),
            "by_domain": {r["domain"]: r for r in rows}
        }

    # -------------------------
    # UPDATE
    # -------------------------
    def update_status(self, alert_id: UUID, clerk_user_id: str, status: str):
        
        sql = """
            UPDATE alerts
            SET status = :status,
                updated_at = NOW()
            WHERE alert_id = :id
            AND clerk_user_id = :user
            RETURNING *
        """

        params = [
            {
                "name": "id",
                "value": {"stringValue": str(alert_id)},
                "typeHint": "UUID"
            },
            {
                "name": "user",
                "value": {"stringValue": clerk_user_id}
            },
            {
                "name": "status",
                "value": {"stringValue": status}
            }
        ]

        return self.db.query_raw(sql, params)

    # -------------------------
    # HELPERS
    # -------------------------
    def _build_params(self, alert: Dict):
        return self._query_params(
            user=alert["clerk_user_id"],
            symbol=alert.get("symbol"),
            domain=alert["domain"],
            category=alert["category"],
            severity=alert["severity"],
            title=alert["title"],
            message=alert["message"],
            rationale=alert.get("rationale")
        )

    def _query_params(self, **kwargs):
        params = []
        for k, v in kwargs.items():
            if v is None:
                params.append({"name": k, "value": {"isNull": True}})
            else:
                params.append({"name": k, "value": {"stringValue": str(v)}})
        return params

    def _bind_param(self, name: str, value):
        """
        Build Aurora Data API parameter with correct type.
        """
        if value is None:
            return {"name": name, "value": {"isNull": True}}

        if isinstance(value, bool):
            return {"name": name, "value": {"booleanValue": value}}

        if isinstance(value, int):
            return {"name": name, "value": {"longValue": value}}

        if isinstance(value, float):
            return {"name": name, "value": {"doubleValue": value}}

        return {"name": name, "value": {"stringValue": str(value)}}


    def update_intel_fields(self, alert_id: str, updates: Dict):
        """
        Apply decision-engine fields to an existing alert row.
        Only updates known columns; ignores anything extra in `updates`.
        """
        allowed_keys = {
            "severity",
            "action_required",
            "confidence_score",
            "action_hint",
            "rationale",
            "status",
        }

        set_clauses = []
        params = []

        for key, value in updates.items():
            if key not in allowed_keys:
                continue
            set_clauses.append(f"{key} = :{key}")
            params.append(self._bind_param(key, value))

        if not set_clauses:
            return

        sql = f"""
            UPDATE alerts
            SET {", ".join(set_clauses)},
                updated_at = NOW()
            WHERE alert_id = :id
        """

        params.append({
        "name": "id",
        "value": {"stringValue": str(alert_id)},
        "typeHint": "UUID"
        })
        self.db.query_raw(sql, params)

