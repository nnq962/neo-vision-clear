"""Kiểm thử detector bằng relative depth tổng hợp."""

import unittest

import numpy as np

from walkway_monitor.config import DetectionConfig
from walkway_monitor.detection.detector import OccupancyDetector
from walkway_monitor.detection.models import OccupancyState
from walkway_monitor.models import BaselineArtifact, RoiDefinition


def make_baseline() -> BaselineArtifact:
    """Tạo baseline gradient với ROI nằm giữa frame cho các test detector."""
    height, width = 60, 80
    reference = np.linspace(
        0.1,
        2.0,
        height * width,
        dtype=np.float32,
    ).reshape(height, width)
    roi = RoiDefinition(
        normalized_points=np.array(
            [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]],
            dtype=np.float32,
        )
    )
    return BaselineArtifact(
        reference_depth=reference,
        noise_map=np.zeros_like(reference),
        roi=roi,
        frame_width=width,
        frame_height=height,
        encoder="vits",
        input_size=518,
        frame_count=60,
        created_at="2026-09-04T00:00:00+00:00",
        source_type="VIDEO",
        alignment_median_error=0.0,
        noise_p99=0.0,
    )


class OccupancyDetectorTestCase(unittest.TestCase):
    """Kiểm tra CLEAR, OCCUPIED và UNKNOWN của detector."""

    def setUp(self) -> None:
        """Tạo baseline và detector có thời gian xác nhận ngắn cho từng test."""
        self.baseline = make_baseline()
        self.config = DetectionConfig(
            minimum_area_ratio=0.02,
            occupied_frames=2,
            clear_frames=2,
            camera_change_area_ratio=0.10,
        )
        self.detector = OccupancyDetector(self.baseline, self.config)

    # ─────────────────────────────────────────────────────────────────────────

    def test_static_obstacle_stays_occupied(self) -> None:
        """Vật đứng yên trong ROI phải chuyển và giữ trạng thái OCCUPIED."""
        clear_depth = self.baseline.reference_depth.copy()
        first_clear = self.detector.process(clear_depth)
        second_clear = self.detector.process(clear_depth)
        self.assertEqual(first_clear.result.state, OccupancyState.UNKNOWN)
        self.assertEqual(second_clear.result.state, OccupancyState.CLEAR)

        occupied_depth = clear_depth.copy()
        occupied_depth[20:40, 30:50] += 0.5
        first_occupied = self.detector.process(occupied_depth)
        second_occupied = self.detector.process(occupied_depth)
        third_occupied = self.detector.process(occupied_depth)
        self.assertEqual(first_occupied.result.state, OccupancyState.CLEAR)
        self.assertEqual(second_occupied.result.state, OccupancyState.OCCUPIED)
        self.assertEqual(third_occupied.result.state, OccupancyState.OCCUPIED)
        self.assertEqual(int(np.count_nonzero(first_occupied.changed_mask)), 0)
        self.assertEqual(int(np.count_nonzero(second_occupied.changed_mask)), 0)
        self.assertGreater(int(np.count_nonzero(third_occupied.changed_mask)), 0)
        self.assertGreater(second_occupied.result.largest_area_ratio, 0.02)

    # ─────────────────────────────────────────────────────────────────────────

    def test_large_outside_change_returns_unknown(self) -> None:
        """Thay đổi phi tuyến trên phần lớn vùng ngoài ROI phải trả UNKNOWN."""
        depth = self.baseline.reference_depth.copy()
        roi = self.baseline.roi.to_mask(
            self.baseline.frame_width,
            self.baseline.frame_height,
        ) > 0
        rows, columns = np.indices(depth.shape)
        pattern = np.where((rows + columns) % 2 == 0, 0.7, -0.7).astype(np.float32)
        depth[~roi] += pattern[~roi]
        output = self.detector.process(depth)
        self.assertEqual(output.result.state, OccupancyState.UNKNOWN)
        self.assertEqual(output.result.reason, "camera_or_scene_changed")
        self.assertGreater(output.result.outside_change_ratio, 0.10)


if __name__ == "__main__":
    unittest.main()
