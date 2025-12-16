from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class AlertOut(BaseModel):
    alert_id: UUID
    clerk_user_id: str
    job_id: Optional[UUID] = None
    symbol: Optional[str] = None

    domain: str
    category: str
    severity: str

    title: str
    message: str
    rationale: Optional[str] = None
    status: str

    created_at: datetime

    class Config:
        orm_mode = True
