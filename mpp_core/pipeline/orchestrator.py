from datetime import datetime

from mpp_core.compliance.engine import ComplianceEngine
from mpp_core.domain.enums import PipelineStage, ProductStatus
from mpp_core.domain.models import Attribute, Product, SKU
from mpp_core.enrichment.service import EnrichmentService
from mpp_core.export.base import BaseMarketplaceExporter
from mpp_core.export.payload import PayloadBuilder
from mpp_core.ingestion.base import BaseIngestionClient
from mpp_core.ingestion.dto import RawProductDTO
from mpp_core.mapping.mappers import AttributeMapper, CategoryMapper
from mpp_core.storage.repositories import PipelineEvent, PipelineEventRepository, ProductRepository


class PipelineOrchestrator:
    def __init__(
        self,
        ingestion_client: BaseIngestionClient,
        compliance_engine: ComplianceEngine,
        category_mapper: CategoryMapper,
        attribute_mapper: AttributeMapper,
        enrichment_service: EnrichmentService,
        payload_builder: PayloadBuilder,
        exporter: BaseMarketplaceExporter,
        product_repository: ProductRepository,
        event_repository: PipelineEventRepository,
    ) -> None:
        self._ingestion_client = ingestion_client
        self._compliance_engine = compliance_engine
        self._category_mapper = category_mapper
        self._attribute_mapper = attribute_mapper
        self._enrichment_service = enrichment_service
        self._payload_builder = payload_builder
        self._exporter = exporter
        self._product_repository = product_repository
        self._event_repository = event_repository

    def run_once(self) -> list[Product]:
        processed_products: list[Product] = []

        for raw_product in self._ingestion_client.fetch_products():
            product = self._to_domain_model(raw_product)
            self._set_state(product, stage=PipelineStage.INGESTION, status=ProductStatus.INGESTED)

            compliance = self._compliance_engine.check(product)
            if not compliance.approved:
                product.rejection_reason = compliance.reason
                self._set_state(
                    product,
                    stage=PipelineStage.COMPLIANCE,
                    status=ProductStatus.COMPLIANCE_REJECTED,
                    event_message=compliance.reason or "Compliance check failed",
                )
                processed_products.append(product)
                continue

            self._set_state(product, stage=PipelineStage.COMPLIANCE, status=ProductStatus.COMPLIANCE_PASSED)

            self._category_mapper.map(product, raw_product.source_category_id)
            self._attribute_mapper.map(product)
            self._set_state(product, stage=PipelineStage.MAPPING, status=ProductStatus.MAPPED)

            self._enrichment_service.enrich(product)
            self._set_state(product, stage=PipelineStage.ENRICHMENT, status=ProductStatus.ENRICHED)

            self._set_state(product, stage=PipelineStage.EXPORT, status=ProductStatus.READY_FOR_EXPORT)
            payload = self._payload_builder.build(product)
            export_result = self._exporter.export(payload)

            if export_result.success:
                product.external_export_id = export_result.external_id
                self._set_state(product, stage=PipelineStage.EXPORT, status=ProductStatus.EXPORTED)
            else:
                product.rejection_reason = export_result.message
                self._set_state(
                    product,
                    stage=PipelineStage.EXPORT,
                    status=ProductStatus.FAILED,
                    event_message=export_result.message,
                )

            processed_products.append(product)

        return processed_products

    def _set_state(
        self,
        product: Product,
        stage: PipelineStage,
        status: ProductStatus,
        event_message: str = "",
    ) -> None:
        product.current_stage = stage
        product.status = status
        self._product_repository.save(product)
        self._event_repository.add(
            PipelineEvent(
                source_product_id=product.source_product_id,
                stage=stage,
                status=status,
                created_at=datetime.utcnow(),
                message=event_message,
            )
        )

    @staticmethod
    def _to_domain_model(raw: RawProductDTO) -> Product:
        attributes = [
            Attribute(name=key, value=value, source_name=key)
            for key, value in raw.raw_attributes.items()
        ]
        skus = [
            SKU(sku_id=sku.sku_id, price=sku.price, currency=sku.currency, stock=sku.stock)
            for sku in raw.skus
        ]
        return Product(
            source_product_id=raw.source_product_id,
            title=raw.title,
            description=raw.description,
            attributes=attributes,
            skus=skus,
            image_urls=list(raw.image_urls),
        )
