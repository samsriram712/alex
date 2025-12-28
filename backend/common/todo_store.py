from src.models import Database
from typing import List, Dict, Optional
from uuid import UUID
from datetime import datetime, timezone


class TodoStore:

    def __init__(self):
        self.db = Database()

    # -------------------------
    # INSERT
    # -------------------------
    def insert_todo(self, todo: Dict) -> None:
        sql = """
            INSERT INTO todos (
                todo_id, clerk_user_id, job_id, symbol,
                domain, title, description, rationale,
                action_type, priority, due_at, source_alert_id
            )
            VALUES (
                uuid_generate_v4(), :user, :job, :symbol,
                :domain, :title, :description, :rationale,
                :action_type, :priority, :due_at, :source_alert_id
            )
        """
        params = self._build_params(todo)
        
        self.db.query_raw(sql, params)

    def insert_bulk(self, todos: List[Dict]) -> None:
        for todo in todos:
            self.insert_todo(todo)

    # -------------------------
    # QUERY
    # -------------------------
    def list_todos(self,
                   clerk_user_id: str,
                   symbol: Optional[str] = None,
                   domain: Optional[str] = None,
                   status: Optional[str] = None,
                   job_id: Optional[UUID] = None,
                   include_dismissed: bool = False,
                   limit: int = 50):

        sql = """
            SELECT *
            FROM todos
            WHERE clerk_user_id = :user
                AND (:symbol::varchar IS NULL OR symbol = :symbol::varchar)
                AND (:domain::varchar IS NULL OR domain = :domain::varchar)
                AND (:include_dismissed::boolean = TRUE OR status != 'dismissed')
                AND (:status::varchar IS NULL OR status = :status::varchar)
                AND (:job_id::uuid IS NULL OR job_id = :job_id::uuid)
            ORDER BY created_at
        """
        sql += f" LIMIT {int(limit)}"

        return self.db.query_raw(sql, self._query_params(
            user=clerk_user_id,
            symbol=symbol,
            domain=domain,
            status=status,
            job_id=job_id,
            include_dismissed=include_dismissed
        ))

    # -------------------------
    # UPDATE
    # -------------------------
    def update_status(self, todo_id: UUID, clerk_user_id: str, status: str):
                
        sql = """
            UPDATE todos
            SET status = :status,
                updated_at = NOW()
            WHERE todo_id = :id
            AND clerk_user_id = :user
            RETURNING *
            """

        params = [
            {
                "name": "id",
                "value": {"stringValue": str(todo_id)},
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

    def _bind_param(self, name: str, value):
        """Bind Aurora parameters using correct native types."""
        if value is None:
            return {"name": name, "value": {"isNull": True}}

        # ✅ TIMESTAMP (for 'timestamp without time zone' columns)
        if isinstance(value, datetime):
            # Normalize to UTC then DROP timezone (db column is without time zone)
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)

            return {
                "name": name,
                "value": {"stringValue": value.strftime("%Y-%m-%d %H:%M:%S")},
                "typeHint": "TIMESTAMP"
            }

        # ✅ boolean
        if isinstance(value, bool):
            return {"name": name, "value": {"booleanValue": value}}

        # ✅ integer
        if isinstance(value, int):
            return {"name": name, "value": {"longValue": value}}

        # ✅ float
        if isinstance(value, float):
            return {"name": name, "value": {"doubleValue": value}}

        # ✅ UUID
        if isinstance(value, UUID):
            return {
                "name": name,
                "value": {"stringValue": str(value)},
                "typeHint": "UUID"
            }

        # ✅ UUID string
        if isinstance(value, str):
            try:
                uuid_val = UUID(value)  # validate
                return {
                    "name": name,
                    "value": {"stringValue": value},
                    "typeHint": "UUID"
                }
            except ValueError:
                pass

        # ✅ fallback string
        return {"name": name, "value": {"stringValue": str(value)}}
    
    def _build_params(self, todo: Dict):
        return self._query_params(
            user=todo["clerk_user_id"],
            job=todo.get("job_id"),  
            symbol=todo.get("symbol"),
            domain=todo["domain"],
            title=todo["title"],
            description=todo["description"],
            rationale=todo.get("rationale"),
            action_type=todo["action_type"],
            priority=todo["priority"],
            due_at=todo.get("due_at"),
            source_alert_id=todo.get("source_alert_id")
        )

    def _query_params(self, **kwargs):
        # params = []
        # for k, v in kwargs.items():
            # if v is None:
                # params.append({"name": k, "value": {"isNull": True}})
            # else:
                # params.append({"name": k, "value": {"stringValue": str(v)}})
        # return params
        return [self._bind_param(k, v) for k, v in kwargs.items()]

    def list_open_for_user_and_symbol(self, clerk_user_id: str, job_id: str, symbol: Optional[str],):
        sql = """
            SELECT *
            FROM todos
            WHERE clerk_user_id = :user
            AND (:symbol::varchar IS NULL OR symbol = :symbol::varchar)
            AND status IN ('open','in_progress')
        """
        params = [
            {"name": "user", "value": {"stringValue": clerk_user_id}},
            ]
        if symbol is None:
            params.append({"name": "symbol", "value": {"isNull": True}})
        else:
            params.append({"name": "symbol", "value": {"stringValue": symbol}})
        return self.db.query_raw(sql, params)

