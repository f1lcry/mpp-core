from typing import Any, Optional

_MAIN_IMAGE_KEYS = ("img_url", "imageUrl", "image_url", "url", "big")
_SKU_IMAGE_KEYS = ("imageUrl", "image_url", "img_url")


def normalize_product_images(
    raw_product: dict[str, Any],
    *,
    placeholder_image_url: str,
) -> list[str]:
    primary_images = _extract_main_images(raw_product.get("images"))
    if primary_images:
        return primary_images

    sku_images = _extract_sku_images(raw_product.get("sku"))
    if sku_images:
        return sku_images

    fallback = _normalize_image_url(placeholder_image_url)
    if fallback is None:
        return []
    return [fallback]


def _extract_main_images(raw_images: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(raw_images, str):
        _append_normalized_url(urls, raw_images)
        return _deduplicate_preserve_order(urls)

    if not isinstance(raw_images, list):
        return []

    for image in raw_images:
        if isinstance(image, str):
            _append_normalized_url(urls, image)
            continue

        if not isinstance(image, dict):
            continue

        for key in _MAIN_IMAGE_KEYS:
            if key not in image:
                continue
            _append_normalized_url(urls, image.get(key))
            break

    return _deduplicate_preserve_order(urls)


def _extract_sku_images(raw_sku: Any) -> list[str]:
    urls: list[str] = []
    _walk_sku(raw_sku, urls)
    return _deduplicate_preserve_order(urls)


def _walk_sku(node: Any, urls: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_sku(item, urls)
        return

    if not isinstance(node, dict):
        return

    for key, value in node.items():
        if key in _SKU_IMAGE_KEYS:
            _append_normalized_url(urls, value)
        if isinstance(value, (dict, list)):
            _walk_sku(value, urls)


def _append_normalized_url(urls: list[str], raw_value: Any) -> None:
    normalized = _normalize_image_url(raw_value)
    if normalized is None:
        return
    urls.append(normalized)


def _normalize_image_url(raw_value: Any) -> Optional[str]:
    if raw_value is None:
        return None
    image_url = str(raw_value).strip()
    if not image_url:
        return None
    if image_url.startswith("//"):
        image_url = f"https:{image_url}"
    if image_url.startswith(("http://", "https://")):
        return image_url
    return None


def _deduplicate_preserve_order(image_urls: list[str]) -> list[str]:
    deduplicated: list[str] = []
    seen: set[str] = set()
    for image_url in image_urls:
        if image_url in seen:
            continue
        seen.add(image_url)
        deduplicated.append(image_url)
    return deduplicated
