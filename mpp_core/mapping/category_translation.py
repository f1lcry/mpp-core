import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from mpp_core.storage.sqlite.product_repository import SqliteProductRepository

DEFAULT_TRANSLATION_DICTIONARY: dict[str, str] = {
    "卷尺": "tape_measure",
    "电动螺丝刀": "electric_screwdriver",
    "角磨机": "angle_grinder",
    "201372301": "collectible_toys",
    "124740029": "shoe_covers",
    "201909501": "camping_accessories",
    "201771102": "keyboard_switches",
    "201754501": "disposable_bed_sheets",
    "201689102": "warming_patches",
    "201353014": "lighters",
    "125062013": "dental_travel_kits",
}


@dataclass
class CategoryTranslationResult:
    candidates: int
    translated: int
    skipped: int


class CategoryTranslationService:
    def __init__(
        self,
        *,
        dictionary_path: Path = Path("data/category_translation.json"),
        translation_dictionary: Optional[dict[str, str]] = None,
    ) -> None:
        self._translation_dictionary = (
            translation_dictionary
            if translation_dictionary is not None
            else self._load_translation_dictionary(dictionary_path)
        )
        self._normalized_pairs = [
            (self._normalize(keyword), internal_category)
            for keyword, internal_category in self._translation_dictionary.items()
            if self._normalize(keyword) and internal_category.strip()
        ]
        self._normalized_pairs.sort(key=lambda pair: len(pair[0]), reverse=True)

    def run(self, repository: SqliteProductRepository) -> CategoryTranslationResult:
        products = repository.get_products_by_status("new")

        translated = 0
        skipped = 0
        for product in products:
            source_text = self._build_source_text(product)
            internal_category = self._resolve_internal_category(source_text)
            if internal_category is None:
                skipped += 1
                continue

            if repository.update_translation(product.item_id_1688, internal_category):
                translated += 1
            else:
                skipped += 1

        return CategoryTranslationResult(
            candidates=len(products),
            translated=translated,
            skipped=skipped,
        )

    def _resolve_internal_category(self, source_text: str) -> Optional[str]:
        normalized_source = self._normalize(source_text)
        if not normalized_source:
            return None

        for normalized_keyword, internal_category in self._normalized_pairs:
            if normalized_keyword in normalized_source:
                return internal_category
        return None

    @staticmethod
    def _build_source_text(product: object) -> str:
        parts = [
            str(getattr(product, "category_path_1688", "") or ""),
            str(getattr(product, "category_1688", "") or ""),
            str(getattr(product, "title", "") or ""),
            str(getattr(product, "title_raw", "") or ""),
        ]
        return " | ".join(parts)

    @staticmethod
    def _normalize(value: str) -> str:
        text = value.strip().lower()
        return "".join(text.split())

    @staticmethod
    def _load_translation_dictionary(dictionary_path: Path) -> dict[str, str]:
        if not dictionary_path.exists():
            return dict(DEFAULT_TRANSLATION_DICTIONARY)

        try:
            payload = json.loads(dictionary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return dict(DEFAULT_TRANSLATION_DICTIONARY)

        if not isinstance(payload, dict):
            return dict(DEFAULT_TRANSLATION_DICTIONARY)

        dictionary: dict[str, str] = {}
        for raw_key, raw_value in payload.items():
            key = str(raw_key).strip()
            value = str(raw_value).strip()
            if not key or not value:
                continue
            dictionary[key] = value

        if not dictionary:
            return dict(DEFAULT_TRANSLATION_DICTIONARY)
        return dictionary
