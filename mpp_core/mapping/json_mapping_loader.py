import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OzonCategoryMapping:
    category_id: int
    type_id: int
    attributes: dict[str, int]
    required_attributes: list[str] = field(default_factory=list)
    default_values: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "OzonCategoryMapping":
        try:
            category_id = int(raw["category_id"])
            type_id = int(raw["type_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Mapping must contain integer 'category_id' and 'type_id'") from exc

        raw_attributes = raw.get("attributes")
        if not isinstance(raw_attributes, dict) or not raw_attributes:
            raise ValueError("Mapping field 'attributes' must be a non-empty object")

        normalized_attributes: dict[str, int] = {}
        for key, value in raw_attributes.items():
            try:
                normalized_attributes[str(key)] = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Attribute id for '{key}' must be an integer") from exc

        required_raw = raw.get("required_attributes")
        if required_raw is None:
            required_attributes = list(normalized_attributes.keys())
        elif isinstance(required_raw, list):
            required_attributes = [str(attribute_name) for attribute_name in required_raw]
        else:
            raise ValueError("Mapping field 'required_attributes' must be a list when provided")

        default_values_raw = raw.get("default_values") or {}
        if not isinstance(default_values_raw, dict):
            raise ValueError("Mapping field 'default_values' must be an object when provided")
        default_values = {
            str(attribute_name): str(value)
            for attribute_name, value in default_values_raw.items()
        }

        return cls(
            category_id=category_id,
            type_id=type_id,
            attributes=normalized_attributes,
            required_attributes=required_attributes,
            default_values=default_values,
        )


class JsonMappingLoader:
    def __init__(self, mapping_path: Path) -> None:
        self._mapping_path = mapping_path
        self._mapping = self._load_mapping()

    def get_by_category(self, category: str) -> OzonCategoryMapping:
        mapping = self._mapping.get(category)
        if mapping is None:
            raise KeyError(
                f"Mapping for category '{category}' is missing in {self._mapping_path}"
            )
        return mapping

    def _load_mapping(self) -> dict[str, OzonCategoryMapping]:
        if not self._mapping_path.is_file():
            raise FileNotFoundError(f"Mapping file not found: {self._mapping_path}")

        raw_text = self._mapping_path.read_text(encoding="utf-8")
        try:
            raw_mapping = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {self._mapping_path}") from exc

        if not isinstance(raw_mapping, dict):
            raise ValueError("Mapping JSON root must be an object")

        parsed: dict[str, OzonCategoryMapping] = {}
        for category, category_mapping in raw_mapping.items():
            if not isinstance(category_mapping, dict):
                raise ValueError(
                    f"Mapping for category '{category}' must be an object"
                )
            parsed[str(category)] = OzonCategoryMapping.from_dict(category_mapping)
        return parsed
