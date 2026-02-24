from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InternalProduct:
    category: str
    title: str
    description: str
    price: float
    attributes: dict[str, Any] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "InternalProduct":
        category = str(raw.get("category", "")).strip()
        title = str(raw.get("title", "")).strip()
        description = str(raw.get("description", "")).strip()
        attributes = raw.get("attributes") or {}
        images = raw.get("images") or []

        if not category:
            raise ValueError("Product 'category' is required")
        if not title:
            raise ValueError("Product 'title' is required")
        if not description:
            raise ValueError("Product 'description' is required")
        if not isinstance(attributes, dict):
            raise ValueError("Product 'attributes' must be an object")
        if not isinstance(images, list):
            raise ValueError("Product 'images' must be a list")

        try:
            price = float(raw.get("price"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Product 'price' must be a number") from exc

        normalized_attributes = {str(key): value for key, value in attributes.items()}
        normalized_images = [str(image) for image in images]
        return cls(
            category=category,
            title=title,
            description=description,
            price=price,
            attributes=normalized_attributes,
            images=normalized_images,
        )
