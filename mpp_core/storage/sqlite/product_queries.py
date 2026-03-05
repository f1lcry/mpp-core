from datetime import datetime
from typing import Any, Callable, Optional, Sequence

from mpp_core.storage.sqlite.models import ProductRecord


def get_products_ready_for_export(
    *,
    connection: Any,
    limit: int,
    row_mapper: Callable[[object], Optional[ProductRecord]],
) -> list[ProductRecord]:
    try:
        safe_limit = max(1, int(limit))
    except (TypeError, ValueError):
        safe_limit = 1
    rows = connection.execute(
        """
        SELECT *
        FROM products
        WHERE status = 'ready_for_export'
        ORDER BY id
        LIMIT ?
        """,
        (safe_limit,),
    ).fetchall()

    products: list[ProductRecord] = []
    for row in rows:
        mapped = row_mapper(row)
        if mapped is not None:
            products.append(mapped)
    return products


def update_product_status_exported(
    *,
    connection: Any,
    item_id_1688: str,
    ozon_offer_id: str,
) -> bool:
    updated_at = datetime.utcnow().isoformat()
    if _has_column(connection=connection, table_name="products", column_name="ozon_offer_id"):
        cursor = connection.execute(
            """
            UPDATE products
            SET status = 'exported', ozon_offer_id = ?, updated_at = ?
            WHERE item_id_1688 = ?
            """,
            (ozon_offer_id, updated_at, item_id_1688),
        )
        return cursor.rowcount > 0

    cursor = connection.execute(
        """
        UPDATE products
        SET status = 'exported', updated_at = ?
        WHERE item_id_1688 = ?
        """,
        (updated_at, item_id_1688),
    )
    return cursor.rowcount > 0


def replace_product_images(
    *,
    connection: Any,
    item_id_1688: str,
    image_urls: Sequence[str],
    source: str = "tmapi",
) -> int:
    product_row = connection.execute(
        "SELECT id FROM products WHERE item_id_1688 = ?",
        (item_id_1688,),
    ).fetchone()
    if product_row is None:
        return 0

    product_id = int(product_row["id"])
    normalized_urls = _normalize_image_urls(image_urls)
    source_text = str(source or "tmapi").strip() or "tmapi"

    connection.execute(
        "DELETE FROM product_images WHERE product_id = ?",
        (product_id,),
    )

    if not normalized_urls:
        return 0

    created_at = datetime.utcnow().isoformat()
    payload = [
        (product_id, image_url, position, source_text, created_at)
        for position, image_url in enumerate(normalized_urls)
    ]
    connection.executemany(
        """
        INSERT INTO product_images (
            product_id,
            image_url,
            position,
            source,
            created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        payload,
    )
    return len(payload)


def get_product_images(
    *,
    connection: Any,
    item_id_1688: str,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT pi.image_url
        FROM product_images AS pi
        JOIN products AS p ON p.id = pi.product_id
        WHERE p.item_id_1688 = ?
        ORDER BY pi.position ASC, pi.id ASC
        """,
        (item_id_1688,),
    ).fetchall()
    return [str(row["image_url"]).strip() for row in rows if str(row["image_url"]).strip()]


def get_product_images_by_product_ids(
    *,
    connection: Any,
    product_ids: Sequence[int],
) -> dict[int, list[str]]:
    normalized_ids = _normalize_product_ids(product_ids)
    if not normalized_ids:
        return {}

    placeholders = ", ".join("?" for _ in normalized_ids)
    rows = connection.execute(
        f"""
        SELECT product_id, image_url
        FROM product_images
        WHERE product_id IN ({placeholders})
        ORDER BY product_id ASC, position ASC, id ASC
        """,
        tuple(normalized_ids),
    ).fetchall()

    images_by_product_id: dict[int, list[str]] = {product_id: [] for product_id in normalized_ids}
    for row in rows:
        product_id = int(row["product_id"])
        image_url = str(row["image_url"]).strip()
        if not image_url:
            continue
        images_by_product_id.setdefault(product_id, []).append(image_url)
    return images_by_product_id


def _has_column(*, connection: Any, table_name: str, column_name: str) -> bool:
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(column["name"]) == column_name for column in columns)


def _normalize_image_urls(image_urls: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_url in image_urls:
        image_url = str(raw_url or "").strip()
        if not image_url:
            continue
        if image_url.startswith("//"):
            image_url = f"https:{image_url}"
        if image_url in seen:
            continue
        seen.add(image_url)
        normalized.append(image_url)
    return normalized


def _normalize_product_ids(product_ids: Sequence[int]) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw_product_id in product_ids:
        try:
            product_id = int(raw_product_id)
        except (TypeError, ValueError):
            continue
        if product_id <= 0 or product_id in seen:
            continue
        seen.add(product_id)
        normalized.append(product_id)
    return normalized
