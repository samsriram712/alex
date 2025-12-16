from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


EventSeverity = Literal["info", "low", "medium", "high", "critical"]


class DetectedEvent(BaseModel):
    """
    A normalized description of a financial situation worth surfacing.

    This is the contract between:
      - Event detection (rule-based or AI)
      - Alert/Todo engine
    """

    event_type: str = Field(
        ...,
        description="Machine-readable type, e.g. 'concentration_risk', 'retirement_shortfall'.",
    )
    severity: EventSeverity = Field(
        ...,
        description="Normalized severity level for alerting and filtering.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Detector confidence between 0 and 1.",
    )

    title: str = Field(
        ...,
        description="Short human-readable title to show in Alerts UI.",
    )
    explanation: str = Field(
        ...,
        description="Plain-language explanation of what was detected and why it matters.",
    )

    evidence: List[str] = Field(
        default_factory=list,
        description="Short bullet-point snippets backing the detection.",
    )
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Human-readable next-best actions for the user or advisor.",
    )

    # Source attribution
    source: str = Field(
        ...,
        description="Where this event came from, e.g. 'reporter', 'retirement', 'researcher'.",
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Job ID for traceability.",
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Clerk user id, if known.",
    )
