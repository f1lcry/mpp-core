from dataclasses import dataclass
from typing import Optional


@dataclass
class ExportResult:
    success: bool
    message: str
    external_id: Optional[str] = None
