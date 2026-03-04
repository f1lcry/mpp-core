import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mpp_core.storage.sqlite.product_repository import SqliteProductRepository

DEFAULT_CATEGORY_MAPPING: dict[str, dict[str, int]] = {
    "tape_measure": {"ozon_category_id": 17028629, "type_id": 91705},
    "electric_screwdriver": {"ozon_category_id": 17029110, "type_id": 92311},
    "angle_grinder": {"ozon_category_id": 17030011, "type_id": 92400},
    "collectible_toys": {"ozon_category_id": 17031866, "type_id": 970661},
    "shoe_covers": {"ozon_category_id": 17031663, "type_id": 970585},
    "camping_accessories": {"ozon_category_id": 17032940, "type_id": 971992},
    "keyboard_switches": {"ozon_category_id": 17034100, "type_id": 973155},
    "disposable_bed_sheets": {"ozon_category_id": 17034323, "type_id": 973411},
    "warming_patches": {"ozon_category_id": 17035173, "type_id": 974653},
    "lighters": {"ozon_category_id": 17035638, "type_id": 975277},
    "dental_travel_kits": {"ozon_category_id": 17036089, "type_id": 975934},
}


@dataclass
class CategoryMappingResult:
    candidates: int
    mapped: int
    skipped: int


class CategoryMappingService:
    def __init__(
        self,
        *,
        dictionary_path: Path = Path("data/category_mapping.json"),
        mapping_dictionary: Optional[dict[str, dict[str, int]]] = None,
    ) -> None:
        self._mapping_dictionary = (
            mapping_dictionary
            if mapping_dictionary is not None
            else self._load_mapping_dictionary(dictionary_path)
        )

    def run(self, repository: SqliteProductRepository) -> CategoryMappingResult:
        products = repository.get_products_by_status("translated")

        mapped = 0
        skipped = 0
        for product in products:
            internal_category = str(
                getattr(product, "internal_category", "")
                or getattr(product, "category_internal", "")
                or ""
            ).strip()
            if not internal_category:
                skipped += 1
                continue

            mapping = self._mapping_dictionary.get(internal_category)
            if mapping is None:
                skipped += 1
                continue

            ozon_category_id = mapping["ozon_category_id"]
            ozon_type_id = mapping["type_id"]
            if repository.update_mapping(product.item_id_1688, ozon_category_id, ozon_type_id):
                mapped += 1
            else:
                skipped += 1

        return CategoryMappingResult(
            candidates=len(products),
            mapped=mapped,
            skipped=skipped,
        )

    @staticmethod
    def promote_to_ready_for_export(repository: SqliteProductRepository) -> int:
        mapped_products = repository.get_products_by_status("mapped")
        promoted = 0
        for product in mapped_products:
            if repository.update_product_status(product.item_id_1688, "ready_for_export"):
                promoted += 1
        return promoted

    @staticmethod
    def _load_mapping_dictionary(dictionary_path: Path) -> dict[str, dict[str, int]]:
        if not dictionary_path.exists():
            return dict(DEFAULT_CATEGORY_MAPPING)

        try:
            payload = json.loads(dictionary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return dict(DEFAULT_CATEGORY_MAPPING)

        if not isinstance(payload, dict):
            return dict(DEFAULT_CATEGORY_MAPPING)

        mapping: dict[str, dict[str, int]] = {}
        for raw_internal_category, raw_values in payload.items():
            internal_category = str(raw_internal_category).strip()
            if not internal_category or not isinstance(raw_values, dict):
                continue

            ozon_category_id = CategoryMappingService._to_int(raw_values.get("ozon_category_id"))
            ozon_type_id = CategoryMappingService._to_int(raw_values.get("type_id"))
            if ozon_category_id is None or ozon_type_id is None:
                continue

            mapping[internal_category] = {
                "ozon_category_id": ozon_category_id,
                "type_id": ozon_type_id,
            }

        if not mapping:
            return dict(DEFAULT_CATEGORY_MAPPING)
        return mapping

    @staticmethod
    def _to_int(value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
