"""Kiểm thử cách đo bề rộng còn trống của lối đi."""

import unittest

import numpy as np

from walkway_monitor.detection.components import measure_walkway_clearance


class WalkwayClearanceTestCase(unittest.TestCase):
    """Kiểm tra vật sát mép và vật giữa lối đi cho kết quả khác nhau."""

    def setUp(self) -> None:
        """Tạo ROI hình thang để mô phỏng phối cảnh của lối đi."""
        self.roi = np.zeros((40, 60), dtype=np.uint8)
        for row in range(5, 35):
            half_width = 10 + (row - 5) // 2
            self.roi[row, 30 - half_width : 31 + half_width] = 255

    # ─────────────────────────────────────────────────────────────────────────

    def test_side_obstacle_leaves_large_contiguous_gap(self) -> None:
        """Vật sát mép chỉ làm giảm một phần nhỏ bề rộng liên tục."""
        obstacle = np.zeros_like(self.roi)
        for row in range(10, 30):
            columns = np.flatnonzero(self.roi[row])
            obstacle[row, columns[: max(1, columns.size // 4)]] = 255

        clearance = measure_walkway_clearance(obstacle, self.roi, 5)

        self.assertGreater(clearance.minimum_free_width_ratio, 0.70)
        self.assertLess(clearance.obstacle_width_ratio, 0.30)

    # ─────────────────────────────────────────────────────────────────────────

    def test_center_obstacle_splits_free_space(self) -> None:
        """Vật ở giữa làm khoảng trống liên tục nhỏ hơn dù diện tích không lớn."""
        obstacle = np.zeros_like(self.roi)
        for row in range(10, 30):
            columns = np.flatnonzero(self.roi[row])
            quarter = max(1, columns.size // 4)
            center = columns.size // 2
            obstacle[row, columns[center - quarter : center + quarter]] = 255

        clearance = measure_walkway_clearance(obstacle, self.roi, 5)

        self.assertLess(clearance.minimum_free_width_ratio, 0.35)
        self.assertGreater(clearance.obstacle_width_ratio, 0.40)


if __name__ == "__main__":
    unittest.main()
