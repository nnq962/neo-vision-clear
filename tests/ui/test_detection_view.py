"""Kiểm thử heatmap depth dùng trong giao diện detection."""

import unittest

import numpy as np

from walkway_monitor.ui.detection_view import colorize_depth


class DepthHeatmapTestCase(unittest.TestCase):
    """Kiểm tra heatmap có shape và dải màu hợp lệ."""

    def test_colorize_depth_with_fixed_reference_range(self) -> None:
        """Depth 2D phải được chuyển thành ảnh màu BGR ba channel."""
        reference = np.linspace(0.0, 1.0, 600, dtype=np.float32).reshape(20, 30)
        heatmap = colorize_depth(reference, reference)
        self.assertEqual(heatmap.shape, (20, 30, 3))
        self.assertEqual(heatmap.dtype, np.uint8)
        self.assertGreater(len(np.unique(heatmap.reshape(-1, 3), axis=0)), 10)


if __name__ == "__main__":
    unittest.main()
