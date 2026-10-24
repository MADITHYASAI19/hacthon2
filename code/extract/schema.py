"""Common schema for extracted evidence records."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ExtractedRecord:
    file_id: str
    captured_at: Optional[datetime]
    system_id: str
    resource_id: str
    category: str
    file_captured_at: Optional[datetime] = None
    user_ref: str = ""
    identifiers: Dict[str, Any] = field(default_factory=dict)
    state_hint: str = "UNKNOWN"
    raw: Any = None
    source_table: str = ""
