from enum import Enum


class PipelineStage(str, Enum):
    INGESTION = "ingestion"
    COMPLIANCE = "compliance"
    MAPPING = "mapping"
    ENRICHMENT = "enrichment"
    EXPORT = "export"


class ProductStatus(str, Enum):
    NEW = "new"
    INGESTED = "ingested"
    COMPLIANCE_PASSED = "compliance_passed"
    COMPLIANCE_REJECTED = "compliance_rejected"
    MAPPED = "mapped"
    ENRICHED = "enriched"
    READY_FOR_EXPORT = "ready_for_export"
    EXPORTED = "exported"
    FAILED = "failed"
