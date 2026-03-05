import tempfile
import unittest
from pathlib import Path

from mpp_core.storage.sqlite import ProductRecord, SqliteProductRepository


class SqliteProductImagesRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp_dir.name) / "mpp_core_test.db"
        self._repository = SqliteProductRepository(db_path=str(self._db_path))
        self._repository.init_db()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_replace_product_images_replaces_collection_and_preserves_order(self) -> None:
        item_id = "item-1688-001"
        self._create_product(item_id=item_id, status="ready_for_export")

        inserted_first = self._repository.replace_product_images(
            item_id_1688=item_id,
            image_urls=[
                "https://img.example.com/one.jpg",
                "https://img.example.com/two.jpg",
                "https://img.example.com/one.jpg",
                "",
            ],
        )
        self.assertEqual(inserted_first, 2)
        self.assertEqual(
            self._repository.get_product_images(item_id),
            [
                "https://img.example.com/one.jpg",
                "https://img.example.com/two.jpg",
            ],
        )

        inserted_second = self._repository.replace_product_images(
            item_id_1688=item_id,
            image_urls=[
                "//img.example.com/three.jpg",
                "https://img.example.com/four.jpg",
            ],
        )
        self.assertEqual(inserted_second, 2)
        self.assertEqual(
            self._repository.get_product_images(item_id),
            [
                "https://img.example.com/three.jpg",
                "https://img.example.com/four.jpg",
            ],
        )

    def test_product_queries_include_images_for_export(self) -> None:
        ready_item_id = "item-1688-ready"
        new_item_id = "item-1688-new"
        self._create_product(item_id=ready_item_id, status="ready_for_export")
        self._create_product(item_id=new_item_id, status="new")

        self._repository.replace_product_images(
            item_id_1688=ready_item_id,
            image_urls=["https://img.example.com/ready.jpg"],
        )
        self._repository.replace_product_images(
            item_id_1688=new_item_id,
            image_urls=["https://img.example.com/new.jpg"],
        )

        ready_products = self._repository.get_products_ready_for_export(limit=10)
        self.assertEqual(len(ready_products), 1)
        self.assertEqual(ready_products[0].item_id_1688, ready_item_id)
        self.assertEqual(ready_products[0].images, ["https://img.example.com/ready.jpg"])

        fetched = self._repository.get_product_by_1688_id(ready_item_id)
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.images, ["https://img.example.com/ready.jpg"])

    def _create_product(self, *, item_id: str, status: str) -> None:
        self._repository.upsert_product(
            ProductRecord(
                item_id_1688=item_id,
                title="Test product",
                title_raw="Test product",
                category_path_1688="test-category",
                category_1688="test-category",
                status=status,
            )
        )


if __name__ == "__main__":
    unittest.main()
