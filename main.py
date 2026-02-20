from mpp_core.compliance import AlwaysApproveRule, ComplianceEngine
from mpp_core.config import Settings
from mpp_core.domain import Category
from mpp_core.enrichment import EnrichmentService, NoOpImageProcessor, StubAIProvider
from mpp_core.export import OzonExporter, OzonPayloadBuilder
from mpp_core.ingestion import Alibaba1688Client
from mpp_core.mapping import AttributeMapper, CategoryMapper
from mpp_core.pipeline import PipelineOrchestrator
from mpp_core.storage import (
    InMemoryAttributeMappingStore,
    InMemoryCategoryMappingStore,
    InMemoryPipelineEventRepository,
    InMemoryProductRepository,
)


def build_orchestrator(settings: Settings) -> PipelineOrchestrator:
    ingestion_client = Alibaba1688Client(batch_size=settings.ingestion_batch_size)

    compliance_engine = ComplianceEngine(rules=[AlwaysApproveRule()])

    category_mapping_store = InMemoryCategoryMappingStore(
        mapping={
            "1688-cat-home-appliances": Category(
                internal_id="home-kitchen-small-appliances",
                name="Home Kitchen / Small Appliances",
                source_id="1688-cat-home-appliances",
            )
        }
    )
    attribute_mapping_store = InMemoryAttributeMappingStore(
        mapping={"Color": "color", "Voltage": "voltage"}
    )

    category_mapper = CategoryMapper(mapping_store=category_mapping_store)
    attribute_mapper = AttributeMapper(mapping_store=attribute_mapping_store)

    enrichment_service = EnrichmentService(
        ai_provider=StubAIProvider(),
        image_processor=NoOpImageProcessor(),
    )

    payload_builder = OzonPayloadBuilder()
    exporter = OzonExporter()

    product_repository = InMemoryProductRepository()
    event_repository = InMemoryPipelineEventRepository()

    return PipelineOrchestrator(
        ingestion_client=ingestion_client,
        compliance_engine=compliance_engine,
        category_mapper=category_mapper,
        attribute_mapper=attribute_mapper,
        enrichment_service=enrichment_service,
        payload_builder=payload_builder,
        exporter=exporter,
        product_repository=product_repository,
        event_repository=event_repository,
    )


def run_demo() -> None:
    settings = Settings.from_env()
    orchestrator = build_orchestrator(settings)
    processed = orchestrator.run_once()

    print(f"Processed products: {len(processed)}")
    for product in processed:
        print(
            f"- {product.source_product_id} | status={product.status.value} | "
            f"stage={product.current_stage.value} | export_id={product.external_export_id}"
        )


if __name__ == "__main__":
    run_demo()
