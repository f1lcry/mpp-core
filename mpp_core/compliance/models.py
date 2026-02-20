from dataclasses import dataclass
from typing import Optional


@dataclass
class ComplianceCheckResult:
    approved: bool
    reason: Optional[str] = None
