import sys
from pathlib import Path

from mpp_core.compliance import AlwaysApproveRule, ComplianceEngine
from mpp_core.config import Settings
from mpp_core.domain import Category
from mpp_core.enrichment import EnrichmentService, NoOpImageProcessor, StubAIProvider
from mpp_core.export import OzonApiClient, OzonExporter, OzonMvpRunner, OzonPayloadBuilder
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
    exporter = OzonExporter(
        client_id=settings.ozon_seller_client_id,
        api_key=settings.ozon_seller_api_key,
    )

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


def run_ozon_mvp_import() -> None:
    settings = Settings.from_env()
    if not settings.has_ozon_seller_credentials:
        raise RuntimeError(
            "Ozon credentials are required. "
            "Set MPP_OZON_SELLER_CLIENT_ID and MPP_OZON_SELLER_API_KEY in .env"
        )

    client = OzonApiClient(
        client_id=settings.ozon_seller_client_id or "",
        api_key=settings.ozon_seller_api_key or "",
        base_url=settings.ozon_seller_base_url,
        verify_ssl=settings.ozon_verify_ssl,
        timeout_sec=settings.ozon_request_timeout_sec,
    )
    runner = OzonMvpRunner(client=client, logs_dir=Path("logs/ozon"))
    result = runner.run()

    print("Ozon MVP import completed")
    print(f"- offer_id: {result.offer_id}")
    print(f"- task_id: {result.task_id}")
    print(f"- status: {result.import_status}")
    print(f"- description_category_id: {result.description_category_id}")
    print(f"- type_id: {result.type_id}")
    print(f"- request log: {result.request_log_path}")
    print(f"- response log: {result.response_log_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ozon-mvp":
        run_ozon_mvp_import()
    else:
        run_demo()
