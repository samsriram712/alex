from fastapi import APIRouter, Depends, Query
from typing import Optional
from uuid import UUID
from api.schemas.todos import TodoOut
from common.todo_store import TodoStore
from ..dependencies import get_current_user_id

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/todos", tags=["todos"])
logger.info(f"TODOS router ={router}")


@router.get("", response_model=list[TodoOut])
def list_todos(
    symbol: Optional[str] = None,
    domain: Optional[str] = None,
    status: Optional[str] = None,
    job_id: Optional[UUID] = None,
    include_dismissed: bool = Query(False),
    limit: int = Query(50, le=100),
    user: str=Depends(get_current_user_id),
):
    # DEV MODE USER
    # user = {"clerk_user_id": "test_user_001"}

    logger.warning(f"TODOS route hit by user={user}")
    store = TodoStore()
    return store.list_todos(
        clerk_user_id=user,
        symbol=symbol,
        domain=domain,
        status=status,
        job_id=job_id,
        include_dismissed=include_dismissed,
        limit=limit
    )


@router.patch("/{todo_id}")
def update_todo_status(todo_id: UUID, status: str, user: str=Depends(get_current_user_id)):
    store = TodoStore()
    return store.update_status(todo_id, user, status)
