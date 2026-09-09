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
    """Kiểm tra kết luận tức thời CLEAR và OCCUPIED của detector."""

    def setUp(self) -> None:
        """Tạo baseline và detector dùng chung cho từng test."""
        self.baseline = make_baseline()
        self.config = DetectionConfig(minimum_free_width_ratio=0.55)
        self.detector = OccupancyDetector(self.baseline, self.config)

    # ─────────────────────────────────────────────────────────────────────────

    def test_static_obstacle_stays_occupied(self) -> None:
        """Vật đứng yên trong ROI phải chuyển và giữ trạng thái OCCUPIED."""
        clear_depth = self.baseline.reference_depth.copy()
        clear_output = self.detector.process(clear_depth)
        self.assertEqual(clear_output.result.state, OccupancyState.CLEAR)

        occupied_depth = clear_depth.copy()
        occupied_depth[20:40, 30:50] += 0.5
        occupied_output = self.detector.process(occupied_depth)
        self.assertEqual(occupied_output.result.state, OccupancyState.OCCUPIED)
        self.assertGreater(int(np.count_nonzero(occupied_output.changed_mask)), 0)
        self.assertGreater(occupied_output.result.largest_area_ratio, 0.02)
        self.assertAlmostEqual(occupied_output.result.alignment_scale, 1.0, places=4)
        self.assertAlmostEqual(occupied_output.result.alignment_shift, 0.0, places=4)

    # ─────────────────────────────────────────────────────────────────────────

    def test_global_scale_and_shift_do_not_create_false_obstacle(self) -> None:
        """Depth trôi affine toàn cục vẫn phải cho kết quả CLEAR ngay lập tức."""
        reference = self.baseline.reference_depth
        drifted_depth = (reference - 0.35) / 1.4

        output = self.detector.process(drifted_depth)

        self.assertEqual(output.result.state, OccupancyState.CLEAR)
        self.assertEqual(int(np.count_nonzero(output.changed_mask)), 0)
        self.assertAlmostEqual(output.result.alignment_scale, 1.4, places=4)
        self.assertAlmostEqual(output.result.alignment_shift, 0.35, places=4)

    # ─────────────────────────────────────────────────────────────────────────

    def test_alignment_can_be_disabled(self) -> None:
        """Khi tắt alignment, detector phải giữ nguyên depth raw và hệ số mặc định."""
        detector = OccupancyDetector(
            self.baseline,
            DetectionConfig(
                depth_alignment=False,
            ),
        )
        depth = self.baseline.reference_depth + np.float32(0.5)

        output = detector.process(depth)

        np.testing.assert_array_equal(output.aligned_depth, depth)
        self.assertFalse(output.result.alignment_enabled)
        self.assertEqual(output.result.alignment_scale, 1.0)
        self.assertEqual(output.result.alignment_shift, 0.0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_long_obstacle_near_edge_keeps_walkway_clear(self) -> None:
        """Vật dài sát mép vẫn CLEAR nếu còn một khoảng trống đủ rộng."""
        detector = OccupancyDetector(
            self.baseline,
            DetectionConfig(
                depth_alignment=False,
                minimum_free_width_ratio=0.55,
            ),
        )
        depth = self.baseline.reference_depth.copy()
        depth[18:42, 20:28] += np.float32(0.5)

        output = detector.process(depth)

        self.assertEqual(output.result.state, OccupancyState.CLEAR)
        self.assertGreater(output.result.largest_area_ratio, 0.05)
        self.assertGreater(output.result.minimum_free_width_ratio, 0.55)

    # ─────────────────────────────────────────────────────────────────────────

    def test_change_outside_check_area_is_ignored(self) -> None:
        """Thay đổi nằm ngoài check area không được ảnh hưởng trạng thái ROI."""
        depth = self.baseline.reference_depth.copy()
        self.detector.process(depth)
        clear_output = self.detector.process(depth)
        self.assertEqual(clear_output.result.state, OccupancyState.CLEAR)

        check_area = clear_output.check_area_mask > 0
        roi = self.baseline.roi.to_mask(
            self.baseline.frame_width,
            self.baseline.frame_height,
        ) > 0
        self.assertGreater(np.count_nonzero(check_area), np.count_nonzero(roi))

        rows, columns = np.indices(depth.shape)
        pattern = np.where((rows + columns) % 2 == 0, 0.7, -0.7).astype(np.float32)
        depth[~check_area] += pattern[~check_area]
        output = self.detector.process(depth)
        self.assertEqual(output.result.state, OccupancyState.CLEAR)
        self.assertEqual(int(np.count_nonzero(output.changed_mask)), 0)
        self.assertEqual(int(np.count_nonzero(output.changed_mask[~roi])), 0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_change_only_in_padding_does_not_occupy_roi(self) -> None:
        """Đồ vật thay đổi trong padding không được làm ROI báo có vật cản."""
        clear_depth = self.baseline.reference_depth.copy()
        first = self.detector.process(clear_depth)
        self.detector.process(clear_depth)
        roi = self.baseline.roi.to_mask(
            self.baseline.frame_width,
            self.baseline.frame_height,
        ) > 0
        padding = (first.check_area_mask > 0) & ~roi

        changed_depth = clear_depth.copy()
        changed_depth[padding] -= 0.5
        first_changed = self.detector.process(changed_depth)
        second_changed = self.detector.process(changed_depth)
        self.assertEqual(first_changed.result.state, OccupancyState.CLEAR)
        self.assertEqual(second_changed.result.state, OccupancyState.CLEAR)
        self.assertEqual(int(np.count_nonzero(second_changed.changed_mask)), 0)


if __name__ == "__main__":
    unittest.main()
