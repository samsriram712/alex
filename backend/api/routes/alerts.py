from fastapi import APIRouter, Depends, Query
from typing import Optional
from uuid import UUID
from api.schemas.alerts import AlertOut
from common.alert_store import AlertStore
from ..dependencies import get_current_user_id

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])
logger.info(f"ALERTS router ={router}")


@router.get("", response_model=list[AlertOut])
def list_alerts(
    symbol: Optional[str] = None,
    domain: Optional[str] = None,
    status: Optional[str] = None,
    job_id: Optional[UUID] = None,
    include_dismissed: bool = Query(False),
    limit: int = Query(50, le=100),
    user: str = Depends(get_current_user_id),
):
    # DEV MODE USER
    # user = {"clerk_user_id": "test_user_001"}
    
    logger.warning(f"ALERTS route hit by user={user}")
    store = AlertStore()
    return store.list_alerts(
        clerk_user_id=user,
        symbol=symbol,
        domain=domain,
        status=status,
        job_id=job_id,
        include_dismissed=include_dismissed,
        limit=limit
    )


@router.get("/summary")
def alert_summary(user: str=Depends(get_current_user_id)):
    store = AlertStore()
    return store.summarize(user)


@router.patch("/{alert_id}")
def update_alert_status(alert_id: UUID, status: str, user: str=Depends(get_current_user_id)):
    store = AlertStore()
    return store.update_status(alert_id, user, status)
