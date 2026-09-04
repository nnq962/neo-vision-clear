"""Kiểm thử chuyển đổi polygon ROI giữa tọa độ chuẩn hóa và pixel."""

import unittest

import numpy as np

from walkway_monitor.calibration.roi_selector import normalize_polygon


class RoiDefinitionTestCase(unittest.TestCase):
    """Kiểm tra phép chuyển tọa độ và tạo mask polygon."""

    def test_polygon_round_trip_and_mask(self) -> None:
        """Polygon pixel phải khôi phục đúng và tạo được mask không rỗng."""
        points = np.array([[0, 0], [99, 0], [99, 49], [0, 49]], dtype=np.float32)
        roi = normalize_polygon(points, width=100, height=50)
        np.testing.assert_array_equal(roi.to_pixel_points(100, 50), points)
        mask = roi.to_mask(100, 50)
        self.assertEqual(mask.shape, (50, 100))
        self.assertEqual(int(np.count_nonzero(mask)), 5000)


if __name__ == "__main__":
    unittest.main()
