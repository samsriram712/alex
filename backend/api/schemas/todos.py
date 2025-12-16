from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class TodoOut(BaseModel):
    todo_id: UUID
    clerk_user_id: str
    job_id: Optional[UUID] = None
    symbol: Optional[str] = None

    domain: str
    title: str
    description: str
    rationale: Optional[str] = None

    action_type: str
    priority: str
    status: str

    due_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        orm_mode = True
