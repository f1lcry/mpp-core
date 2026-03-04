from datetime import datetime
from typing import Any, Callable, Optional

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


def _has_column(*, connection: Any, table_name: str, column_name: str) -> bool:
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(column["name"]) == column_name for column in columns)
