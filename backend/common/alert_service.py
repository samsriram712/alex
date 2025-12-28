# backend/common/alert_service.py

from typing import Any, Dict, List, Optional
from uuid import UUID

from common.alert_engine import AlertDecisionEngine, AlertContext, EngineResult
from common.alert_store import AlertStore
from common.todo_store import TodoStore  # you already use this elsewhere


_engine = AlertDecisionEngine()
_alert_store = AlertStore()
_todo_store = TodoStore()


def emit_alert(ctx: AlertContext) -> EngineResult:
    """
    Central pipeline for alerts:
      1. Insert base alert via AlertStore
      2. Run decision engine
      3. Update alert with engine fields
      4. Optionally create Todo via TodoStore
    """

    # 1) Insert raw alert (baseline severity/status; domain/category/title/message)
    alert_dict: Dict[str, Any] = {
        "clerk_user_id": ctx.clerk_user_id,
        "job_id": ctx.job_id or None,   # if you later bind job_id into context, wire here
        "symbol": ctx.symbol or None,
        "domain": ctx.domain,
        "category": ctx.category,
        "severity": ctx.severity or "info",
        "title": ctx.title,
        "message": ctx.message,
        "rationale": ctx.rationale,
    }

    alert_id = _alert_store.insert_alert(alert_dict)
    ctx.alert_id = str(alert_id) if alert_id else None

    # 2) Decision engine
    result = _engine.evaluate(ctx)

    # 3) Update alert with intelligence fields
    if alert_id:
        _alert_store.update_intel_fields(alert_id, result.alert_updates)

    # 4) Create Todo, with light de-duplication
    if result.todo_spec:
        existing = _todo_store.list_open_for_user_and_symbol(
            clerk_user_id=result.todo_spec.clerk_user_id,
            job_id=result.todo_spec.job_id,
            symbol=result.todo_spec.symbol,
        )
        if _should_create_todo(existing, result.todo_spec):
            _todo_store.insert_todo({
                "clerk_user_id": result.todo_spec.clerk_user_id,
                "job_id": result.todo_spec.job_id,  # can wire job_id into TodoSpec later if needed - DONE
                "symbol": result.todo_spec.symbol,
                "domain": result.todo_spec.domain,
                "title": result.todo_spec.title,
                "description": result.todo_spec.description,
                "rationale": result.todo_spec.rationale,
                "action_type": result.todo_spec.action_type,
                "priority": result.todo_spec.priority,
                "due_at": result.todo_spec.due_at,
                "source_alert_id": alert_id,
            })

    return result


def _should_create_todo(existing_todos: List[Dict[str, Any]], spec) -> bool:
    """
    Avoid creating multiple open/in_progress todos for same symbol + action_type.
    """

    for t in existing_todos:
        if (
            t.get("action_type") == spec.action_type
            and t.get("status") in ("open", "in_progress")
            and t.get("symbol") == spec.symbol
        ):
            return False
    return True
