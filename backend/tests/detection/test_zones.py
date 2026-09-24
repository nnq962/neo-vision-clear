"""Kiểm thử chuyển mask sai khác thành polygon gọn nhẹ cho frontend."""

import unittest

import numpy as np

from walkway_monitor.detection.zones import extract_difference_zones


class DifferenceZonesTestCase(unittest.TestCase):
    """Kiểm tra chuẩn hóa tọa độ và giới hạn kích thước payload zone."""

    def test_extracts_normalized_polygon_from_rectangle(self) -> None:
        """Một vùng chữ nhật phải tạo polygon nằm hoàn toàn trong miền [0, 1]."""
        # Bước 1: tạo vùng thay đổi rõ ràng trên mask có tỷ lệ không vuông.
        mask = np.zeros((50, 100), dtype=np.uint8)
        mask[10:31, 20:61] = 255

        zones = extract_difference_zones(mask)

        # Bước 2: xác nhận polygon có thể scale trực tiếp theo khung video.
        self.assertEqual(len(zones), 1)
        self.assertGreaterEqual(len(zones[0].polygon), 3)
        self.assertTrue(
            all(
                0.0 <= coordinate <= 1.0
                for point in zones[0].polygon
                for coordinate in point
            )
        )
        self.assertAlmostEqual(zones[0].area_ratio, 0.16, places=2)

    # ─────────────────────────────────────────────────────────────────────────

    def test_limits_zone_count_and_polygon_vertices(self) -> None:
        """Extractor phải chặn số zone và số đỉnh để WebSocket không phình to."""
        # Bước 1: tạo nhiều hình tròn rời nhau có contour nhiều đỉnh.
        y_grid, x_grid = np.ogrid[:120, :120]
        mask = np.zeros((120, 120), dtype=np.uint8)
        for center_x, center_y in ((25, 25), (85, 25), (25, 85), (85, 85)):
            mask[(x_grid - center_x) ** 2 + (y_grid - center_y) ** 2 <= 15**2] = 1

        zones = extract_difference_zones(
            mask,
            maximum_zones=2,
            maximum_vertices=6,
        )

        # Bước 2: hard limit phải được giữ cho mọi zone trả về.
        self.assertEqual(len(zones), 2)
        self.assertTrue(all(len(zone.polygon) <= 6 for zone in zones))

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_invalid_mask_shape(self) -> None:
        """Mask có channel màu phải bị từ chối để tránh contour sai hệ tọa độ."""
        with self.assertRaises(ValueError):
            extract_difference_zones(np.zeros((10, 10, 3), dtype=np.uint8))


if __name__ == "__main__":
    unittest.main()
