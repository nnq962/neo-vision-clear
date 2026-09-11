"""Kiểm thử heatmap depth dùng trong giao diện detection."""

import unittest

import numpy as np

from walkway_monitor.config import DetectionConfig
from walkway_monitor.detection.detector import WalkwayAnalyzer
from walkway_monitor.ui.detection_view import colorize_depth, render_detection_view
from tests.detection.test_detector import make_baseline


class DepthHeatmapTestCase(unittest.TestCase):
    """Kiểm tra heatmap có shape và dải màu hợp lệ."""

    def test_colorize_depth_with_fixed_reference_range(self) -> None:
        """Depth 2D phải được chuyển thành ảnh màu BGR ba channel."""
        reference = np.linspace(0.0, 1.0, 600, dtype=np.float32).reshape(20, 30)
        heatmap = colorize_depth(reference, reference)
        self.assertEqual(heatmap.shape, (20, 30, 3))
        self.assertEqual(heatmap.dtype, np.uint8)
        self.assertGreater(len(np.unique(heatmap.reshape(-1, 3), axis=0)), 10)

    # ─────────────────────────────────────────────────────────────────────────

    def test_detection_view_draws_check_area_padding(self) -> None:
        """Giao diện phải vẽ viền check area màu xanh bên ngoài ROI."""
        baseline = make_baseline()
        analyzer = WalkwayAnalyzer(
            baseline,
            DetectionConfig(check_area_padding=6),
        )
        output = analyzer.process(baseline.reference_depth)
        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        view = render_detection_view(frame, baseline, output, fps=10.0)
        self.assertEqual(view.shape, (120, 160, 3))
        cyan = np.array([255, 255, 0], dtype=np.uint8)
        self.assertTrue(np.any(np.all(view[:, :80] == cyan, axis=2)))

    # ─────────────────────────────────────────────────────────────────────────

    def test_detection_view_draws_world_coordinate_labels(self) -> None:
        """Giao diện phải vẽ thêm nhãn khi ROI có tọa độ thực."""
        baseline = make_baseline()
        output = WalkwayAnalyzer(
            baseline,
            DetectionConfig(),
        ).process(baseline.reference_depth)
        frame = np.zeros((60, 80, 3), dtype=np.uint8)

        labeled_view = render_detection_view(
            frame,
            baseline,
            output,
            fps=10.0,
        )

        bev_panel = labeled_view[:60, 80:160]
        yellow = np.array([0, 255, 255], dtype=np.uint8)
        self.assertTrue(np.any(np.all(bev_panel == yellow, axis=2)))

    # ─────────────────────────────────────────────────────────────────────────

    def test_detection_view_can_hide_depth_heatmaps(self) -> None:
        """Giao diện tắt heatmap chỉ còn hàng camera và BEV."""
        baseline = make_baseline()
        analyzer = WalkwayAnalyzer(baseline, DetectionConfig())
        output = analyzer.process(baseline.reference_depth)
        frame = np.zeros((60, 80, 3), dtype=np.uint8)

        view = render_detection_view(
            frame,
            baseline,
            output,
            fps=10.0,
            show_depth_heatmaps=False,
        )

        self.assertEqual(view.shape, (60, 160, 3))


if __name__ == "__main__":
    unittest.main()
