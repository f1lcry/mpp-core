from mpp_core.compliance.models import ComplianceCheckResult
from mpp_core.compliance.rules import ComplianceRule
from mpp_core.domain.models import Product


class ComplianceEngine:
    def __init__(self, rules: list[ComplianceRule]) -> None:
        self._rules = rules

    def check(self, product: Product) -> ComplianceCheckResult:
        for rule in self._rules:
            result = rule.evaluate(product)
            if not result.approved:
                return result
        return ComplianceCheckResult(approved=True)
