from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class ReporterContext:
    """Context for the Reporter agent"""
    job_id: str
    portfolio_data: Dict[str, Any]
    user_data: Dict[str, Any]
    db: Optional[Any] = None # Database connection (optional for testing)
