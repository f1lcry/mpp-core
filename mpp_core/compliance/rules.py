from abc import ABC, abstractmethod

from mpp_core.compliance.models import ComplianceCheckResult
from mpp_core.domain.models import Product


class ComplianceRule(ABC):
    @abstractmethod
    def evaluate(self, product: Product) -> ComplianceCheckResult:
        """Validate product against one compliance policy."""


class AlwaysApproveRule(ComplianceRule):
    """Stub rule used in MVP wiring."""

    def evaluate(self, product: Product) -> ComplianceCheckResult:
        return ComplianceCheckResult(approved=True)
