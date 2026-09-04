"""Kiểm thử việc tổng hợp baseline từ nhiều depth map."""

import unittest

import numpy as np

from walkway_monitor.calibration.baseline_builder import build_baseline
from walkway_monitor.config import CalibrationConfig
from walkway_monitor.models import RoiDefinition


class BaselineBuilderTestCase(unittest.TestCase):
    """Kiểm tra shape, noise và metadata của baseline tổng hợp."""

    def test_build_baseline_aligns_relative_depth_maps(self) -> None:
        """Các depth chỉ khác scale/shift phải tạo noise map gần bằng không."""
        base = np.linspace(0.1, 3.0, 600, dtype=np.float32).reshape(20, 30)
        depth_maps = [
            base * np.float32(scale) + np.float32(shift)
            for scale, shift in [
                (0.9, -0.1),
                (1.0, 0.0),
                (1.1, 0.2),
                (1.05, -0.2),
                (0.95, 0.1),
            ]
        ]
        config = CalibrationConfig(
            frame_count=5,
            input_size=518,
            process_width=960,
            encoder="vits",
        )
        roi = RoiDefinition(
            normalized_points=np.array(
                [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
                dtype=np.float32,
            )
        )
        artifact = build_baseline(depth_maps, roi, config, "VIDEO")
        self.assertEqual(artifact.reference_depth.shape, (20, 30))
        self.assertEqual(artifact.noise_map.shape, (20, 30))
        self.assertLess(artifact.noise_p99, 1e-5)
        self.assertEqual(artifact.source_type, "VIDEO")


if __name__ == "__main__":
    unittest.main()
