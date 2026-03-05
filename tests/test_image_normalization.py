import unittest

from mpp_core.export.ozon_db_payload_builder import DEFAULT_PLACEHOLDER_IMAGE_URL
from mpp_core.pipeline.image_normalization import normalize_product_images


class ImageNormalizationTests(unittest.TestCase):
    def test_uses_main_images_when_present(self) -> None:
        raw_product = {
            "images": [
                " https://img.example.com/main-1.jpg ",
                "",
                "https://img.example.com/main-1.jpg",
                {"url": "https://img.example.com/main-2.jpg"},
            ],
            "sku": [
                {"imageUrl": "https://img.example.com/sku-1.jpg"},
            ],
        }

        images = normalize_product_images(
            raw_product,
            placeholder_image_url=DEFAULT_PLACEHOLDER_IMAGE_URL,
        )

        self.assertEqual(
            images,
            [
                "https://img.example.com/main-1.jpg",
                "https://img.example.com/main-2.jpg",
            ],
        )

    def test_falls_back_to_sku_image_urls(self) -> None:
        raw_product = {
            "images": [],
            "sku": [
                {
                    "values": [
                        {"imageUrl": "https://img.example.com/sku-1.jpg"},
                        {"imageUrl": "//img.example.com/sku-2.jpg"},
                        {"imageUrl": ""},
                    ]
                },
                {"imageUrl": "https://img.example.com/sku-1.jpg"},
            ],
        }

        images = normalize_product_images(
            raw_product,
            placeholder_image_url=DEFAULT_PLACEHOLDER_IMAGE_URL,
        )

        self.assertEqual(
            images,
            [
                "https://img.example.com/sku-1.jpg",
                "https://img.example.com/sku-2.jpg",
            ],
        )

    def test_uses_placeholder_when_no_images_available(self) -> None:
        raw_product = {
            "images": ["", "not_a_url"],
            "sku": [{"values": [{"imageUrl": ""}, {"imageUrl": "ftp://bad-url"}]}],
        }

        images = normalize_product_images(
            raw_product,
            placeholder_image_url=DEFAULT_PLACEHOLDER_IMAGE_URL,
        )

        self.assertEqual(images, [DEFAULT_PLACEHOLDER_IMAGE_URL])


if __name__ == "__main__":
    unittest.main()
