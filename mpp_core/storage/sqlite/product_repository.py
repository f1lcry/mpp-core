from datetime import datetime
from typing import Any, Optional

from mpp_core.storage.sqlite.database import apply_schema, get_connection
from mpp_core.storage.sqlite.models import ProductRecord
from mpp_core.storage.sqlite.product_queries import (
    get_product_images as query_get_product_images,
    get_product_images_by_product_ids,
    get_products_ready_for_export as query_get_products_ready_for_export,
    replace_product_images as query_replace_product_images,
    update_product_status_exported as query_update_product_status_exported,
)

_ALLOWED_STATUSES = {
    "new",
    "translated",
    "mapped",
    "ready_for_export",
    "exported",
}

_REQUIRED_PRODUCTS_COLUMNS: dict[str, str] = {
    "title": "TEXT",
    "category_path_1688": "TEXT",
    "internal_category": "TEXT",
    "ozon_category_id": "INTEGER",
    "ozon_type_id": "INTEGER",
    "ozon_offer_id": "TEXT",
}


class SqliteProductRepository:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path

    def init_db(self) -> None:
        with get_connection(self._db_path) as connection:
            apply_schema(connection)
            self._ensure_products_columns(connection)
            connection.commit()

    def create_product(self, product: ProductRecord) -> ProductRecord:
        self.init_db()
        self._validate_status(product.status)
        now = datetime.utcnow()
        created_at = product.created_at or now
        updated_at = now

        title = product.title or product.title_raw
        category_path_1688 = product.category_path_1688 or product.category_1688
        internal_category = product.internal_category or product.category_internal
        ozon_category_id = product.ozon_category_id if product.ozon_category_id is not None else product.category_ozon

        with get_connection(self._db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO products (
                    item_id_1688,
                    title,
                    title_raw,
                    title_en,
                    title_ru,
                    category_path_1688,
                    category_1688,
                    internal_category,
                    category_internal,
                    ozon_category_id,
                    category_ozon,
                    ozon_type_id,
                    price,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product.item_id_1688,
                    title,
                    product.title_raw,
                    product.title_en,
                    product.title_ru,
                    category_path_1688,
                    product.category_1688,
                    internal_category,
                    internal_category,
                    ozon_category_id,
                    ozon_category_id,
                    product.ozon_type_id,
                    product.price,
                    product.status,
                    created_at.isoformat(),
                    updated_at.isoformat(),
                ),
            )
            connection.commit()

        persisted = self.get_product_by_1688_id(product.item_id_1688)
        if persisted is None:
            raise RuntimeError(f"Failed to create product with item_id_1688={product.item_id_1688}")
        persisted.id = cursor.lastrowid
        return persisted

    def upsert_product(self, product: ProductRecord) -> ProductRecord:
        self.init_db()
        self._validate_status(product.status)
        now = datetime.utcnow()

        title = product.title or product.title_raw
        category_path_1688 = product.category_path_1688 or product.category_1688
        internal_category = product.internal_category or product.category_internal
        ozon_category_id = product.ozon_category_id if product.ozon_category_id is not None else product.category_ozon

        with get_connection(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO products (
                    item_id_1688,
                    title,
                    title_raw,
                    title_en,
                    title_ru,
                    category_path_1688,
                    category_1688,
                    internal_category,
                    category_internal,
                    ozon_category_id,
                    category_ozon,
                    ozon_type_id,
                    price,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id_1688) DO UPDATE SET
                    title = COALESCE(excluded.title, products.title),
                    title_raw = COALESCE(excluded.title_raw, products.title_raw),
                    category_path_1688 = COALESCE(excluded.category_path_1688, products.category_path_1688),
                    category_1688 = COALESCE(excluded.category_1688, products.category_1688),
                    price = COALESCE(excluded.price, products.price),
                    updated_at = excluded.updated_at
                """,
                (
                    product.item_id_1688,
                    title,
                    product.title_raw,
                    product.title_en,
                    product.title_ru,
                    category_path_1688,
                    product.category_1688,
                    internal_category,
                    internal_category,
                    ozon_category_id,
                    ozon_category_id,
                    product.ozon_type_id,
                    product.price,
                    product.status,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            connection.commit()

        persisted = self.get_product_by_1688_id(product.item_id_1688)
        if persisted is None:
            raise RuntimeError(f"Failed to upsert product with item_id_1688={product.item_id_1688}")
        return persisted

    def get_product_by_1688_id(self, item_id: str) -> Optional[ProductRecord]:
        self.init_db()
        with get_connection(self._db_path) as connection:
            row = connection.execute(
                "SELECT * FROM products WHERE item_id_1688 = ?",
                (item_id,),
            ).fetchone()
            product = self._row_to_product(row)
            if product is None:
                return None
            product.images = query_get_product_images(
                connection=connection,
                item_id_1688=item_id,
            )
            return product

    def get_all_products(self) -> list[ProductRecord]:
        self.init_db()
        with get_connection(self._db_path) as connection:
            rows = connection.execute("SELECT * FROM products ORDER BY id ASC").fetchall()
            products = [self._row_to_product(row) for row in rows if row is not None]
            result = [product for product in products if product is not None]
            self._attach_images_to_products(connection=connection, products=result)
            return result

    def get_products_by_status(self, status: str) -> list[ProductRecord]:
        self.init_db()
        self._validate_status(status)
        with get_connection(self._db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM products WHERE status = ? ORDER BY id ASC",
                (status,),
            ).fetchall()
            products = [self._row_to_product(row) for row in rows if row is not None]
            result = [product for product in products if product is not None]
            self._attach_images_to_products(connection=connection, products=result)
            return result

    def get_products_ready_for_export(self, limit: int = 50) -> list[ProductRecord]:
        self.init_db()
        with get_connection(self._db_path) as connection:
            products = query_get_products_ready_for_export(
                connection=connection,
                limit=limit,
                row_mapper=self._row_to_product,
            )
            self._attach_images_to_products(connection=connection, products=products)
            return products

    def update_product_status(self, item_id: str, status: str) -> bool:
        self.init_db()
        self._validate_status(status)
        updated_at = datetime.utcnow().isoformat()
        with get_connection(self._db_path) as connection:
            cursor = connection.execute(
                "UPDATE products SET status = ?, updated_at = ? WHERE item_id_1688 = ?",
                (status, updated_at, item_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def update_product_status_exported(self, item_id_1688: str, ozon_offer_id: str) -> bool:
        self.init_db()
        with get_connection(self._db_path) as connection:
            updated = query_update_product_status_exported(
                connection=connection,
                item_id_1688=item_id_1688,
                ozon_offer_id=ozon_offer_id,
            )
            connection.commit()
            return updated

    def replace_product_images(
        self,
        item_id_1688: str,
        image_urls: list[str],
        source: str = "tmapi",
    ) -> int:
        self.init_db()
        with get_connection(self._db_path) as connection:
            inserted = query_replace_product_images(
                connection=connection,
                item_id_1688=item_id_1688,
                image_urls=image_urls,
                source=source,
            )
            connection.commit()
            return inserted

    def get_product_images(self, item_id_1688: str) -> list[str]:
        self.init_db()
        with get_connection(self._db_path) as connection:
            return query_get_product_images(
                connection=connection,
                item_id_1688=item_id_1688,
            )

    def update_product_translation(self, item_id: str, title_en: Optional[str], title_ru: Optional[str]) -> bool:
        self.init_db()
        updated_at = datetime.utcnow().isoformat()
        with get_connection(self._db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE products
                SET title_en = ?, title_ru = ?, updated_at = ?
                WHERE item_id_1688 = ?
                """,
                (title_en, title_ru, updated_at, item_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def update_product_category(
        self,
        item_id: str,
        category_internal: Optional[str],
        category_ozon: Optional[int],
    ) -> bool:
        self.init_db()
        updated_at = datetime.utcnow().isoformat()
        with get_connection(self._db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE products
                SET internal_category = ?, category_internal = ?, ozon_category_id = ?, category_ozon = ?, updated_at = ?
                WHERE item_id_1688 = ?
                """,
                (category_internal, category_internal, category_ozon, category_ozon, updated_at, item_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def update_translation(self, product_id: str, internal_category: str) -> bool:
        self.init_db()
        clean_internal_category = internal_category.strip()
        if not clean_internal_category:
            return False

        updated_at = datetime.utcnow().isoformat()
        with get_connection(self._db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE products
                SET internal_category = ?, category_internal = ?, status = 'translated', updated_at = ?
                WHERE item_id_1688 = ?
                """,
                (clean_internal_category, clean_internal_category, updated_at, product_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def update_mapping(self, product_id: str, ozon_category_id: int, ozon_type_id: int) -> bool:
        self.init_db()
        updated_at = datetime.utcnow().isoformat()
        with get_connection(self._db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE products
                SET
                    ozon_category_id = ?,
                    category_ozon = ?,
                    ozon_type_id = ?,
                    status = 'mapped',
                    updated_at = ?
                WHERE item_id_1688 = ?
                """,
                (ozon_category_id, ozon_category_id, ozon_type_id, updated_at, product_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def delete_product(self, item_id: str) -> bool:
        self.init_db()
        with get_connection(self._db_path) as connection:
            cursor = connection.execute(
                "DELETE FROM products WHERE item_id_1688 = ?",
                (item_id,),
            )
            connection.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in _ALLOWED_STATUSES:
            allowed = ", ".join(sorted(_ALLOWED_STATUSES))
            raise ValueError(f"Unsupported product status: {status}. Allowed statuses: {allowed}")

    @staticmethod
    def _ensure_products_columns(connection: Any) -> None:
        columns = connection.execute("PRAGMA table_info(products)").fetchall()
        existing_columns = {str(column["name"]) for column in columns}

        for column_name, column_type in _REQUIRED_PRODUCTS_COLUMNS.items():
            if column_name in existing_columns:
                continue
            connection.execute(f"ALTER TABLE products ADD COLUMN {column_name} {column_type}")

    @staticmethod
    def _row_to_product(row: object) -> Optional[ProductRecord]:
        if row is None:
            return None

        row_keys = set(row.keys())

        def read_value(primary_key: str, *fallback_keys: str) -> Any:
            if primary_key in row_keys:
                return row[primary_key]
            for fallback_key in fallback_keys:
                if fallback_key in row_keys:
                    return row[fallback_key]
            return None

        created_at_raw = read_value("created_at")
        updated_at_raw = read_value("updated_at")

        created_at = (
            datetime.fromisoformat(created_at_raw)
            if isinstance(created_at_raw, str)
            else created_at_raw
        )
        updated_at = (
            datetime.fromisoformat(updated_at_raw)
            if isinstance(updated_at_raw, str)
            else updated_at_raw
        )

        return ProductRecord(
            id=read_value("id"),
            item_id_1688=read_value("item_id_1688") or "",
            title=read_value("title", "title_raw"),
            title_raw=read_value("title_raw", "title"),
            title_en=read_value("title_en"),
            title_ru=read_value("title_ru"),
            category_path_1688=read_value("category_path_1688", "category_1688"),
            category_1688=read_value("category_1688", "category_path_1688"),
            internal_category=read_value("internal_category", "category_internal"),
            category_internal=read_value("category_internal", "internal_category"),
            ozon_category_id=read_value("ozon_category_id", "category_ozon"),
            category_ozon=read_value("category_ozon", "ozon_category_id"),
            ozon_type_id=read_value("ozon_type_id"),
            ozon_offer_id=read_value("ozon_offer_id"),
            price=read_value("price"),
            images=[],
            status=read_value("status") or "new",
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _attach_images_to_products(
        *,
        connection: Any,
        products: list[ProductRecord],
    ) -> None:
        if not products:
            return

        product_ids = [product.id for product in products if product.id is not None]
        images_by_product_id = get_product_images_by_product_ids(
            connection=connection,
            product_ids=product_ids,
        )
        for product in products:
            if product.id is None:
                product.images = []
                continue
            product.images = list(images_by_product_id.get(product.id, []))
