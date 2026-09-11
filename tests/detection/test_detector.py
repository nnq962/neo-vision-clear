"""Kiểm thử detector bằng relative depth tổng hợp."""

from dataclasses import replace
import json
import unittest

import numpy as np

from walkway_monitor.config import DetectionConfig
from walkway_monitor.detection.detector import WalkwayAnalyzer
from walkway_monitor.models import BaselineArtifact, RoiDefinition, WorldCoordinates


def make_baseline(with_world_coordinates: bool = True) -> BaselineArtifact:
    """Tạo baseline gradient với ROI nằm giữa frame cho các test detector."""
    height, width = 60, 80
    reference = np.linspace(
        0.1,
        2.0,
        height * width,
        dtype=np.float32,
    ).reshape(height, width)
    world_coordinates = WorldCoordinates(
        points=np.array(
            [[0.0, 0.0], [1.75, 0.0], [1.75, 4.55], [0.0, 4.55]],
            dtype=np.float32,
        ),
        unit="m",
        origin="P1",
        x_axis="Từ trái sang phải",
        y_axis="Từ trên xuống dưới",
    ) if with_world_coordinates else None
    roi = RoiDefinition(
        normalized_points=np.array(
            [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]],
            dtype=np.float32,
        ),
        world_coordinates=world_coordinates,
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


class WalkwayAnalyzerTestCase(unittest.TestCase):
    """Kiểm tra analyzer trả mask và phép đo mà không kết luận trạng thái."""

    def setUp(self) -> None:
        """Tạo baseline và analyzer dùng chung cho từng test."""
        self.baseline = make_baseline()
        self.config = DetectionConfig()
        self.analyzer = WalkwayAnalyzer(self.baseline, self.config)

    # ─────────────────────────────────────────────────────────────────────────

    def test_static_obstacle_produces_changed_mask(self) -> None:
        """Vật đứng yên trong ROI phải tạo mask và số đo khác cảnh trống."""
        clear_depth = self.baseline.reference_depth.copy()
        clear_output = self.analyzer.process(clear_depth)
        self.assertEqual(int(np.count_nonzero(clear_output.changed_mask)), 0)
        self.assertGreater(clear_output.snapshot.maximum_passable_width_meters, 1.7)
        self.assertFalse(hasattr(clear_output.snapshot, "state"))

        occupied_depth = clear_depth.copy()
        occupied_depth[20:40, 30:50] += 0.5
        occupied_output = self.analyzer.process(occupied_depth)
        self.assertGreater(int(np.count_nonzero(occupied_output.changed_mask)), 0)
        self.assertLess(
            occupied_output.snapshot.maximum_passable_width_meters,
            clear_output.snapshot.maximum_passable_width_meters,
        )
        self.assertAlmostEqual(occupied_output.diagnostics.alignment_scale, 1.0, places=4)
        self.assertAlmostEqual(occupied_output.diagnostics.alignment_shift, 0.0, places=4)

    # ─────────────────────────────────────────────────────────────────────────

    def test_global_scale_and_shift_do_not_create_false_obstacle(self) -> None:
        """Depth trôi affine toàn cục không được tạo mask thay đổi giả."""
        reference = self.baseline.reference_depth
        drifted_depth = (reference - 0.35) / 1.4

        output = self.analyzer.process(drifted_depth)

        self.assertEqual(int(np.count_nonzero(output.changed_mask)), 0)
        self.assertAlmostEqual(output.diagnostics.alignment_scale, 1.4, places=4)
        self.assertAlmostEqual(output.diagnostics.alignment_shift, 0.35, places=4)

    # ─────────────────────────────────────────────────────────────────────────

    def test_alignment_can_be_disabled(self) -> None:
        """Khi tắt alignment, detector phải giữ nguyên depth raw và hệ số mặc định."""
        analyzer = WalkwayAnalyzer(
            self.baseline,
            DetectionConfig(
                depth_alignment=False,
            ),
        )
        depth = self.baseline.reference_depth + np.float32(0.5)

        output = analyzer.process(depth)

        np.testing.assert_array_equal(output.aligned_depth, depth)
        self.assertFalse(output.diagnostics.alignment_enabled)
        self.assertEqual(output.diagnostics.alignment_scale, 1.0)
        self.assertEqual(output.diagnostics.alignment_shift, 0.0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_long_obstacle_near_edge_reports_large_free_gap(self) -> None:
        """Vật sát mép phải trả một khoảng trống liên tục lớn ở phía còn lại."""
        analyzer = WalkwayAnalyzer(
            self.baseline,
            DetectionConfig(
                depth_alignment=False,
            ),
        )
        depth = self.baseline.reference_depth.copy()
        depth[18:42, 20:28] += np.float32(0.5)

        output = analyzer.process(depth)

        self.assertGreater(output.snapshot.maximum_passable_width_meters, 1.0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_change_outside_check_area_is_ignored(self) -> None:
        """Thay đổi nằm ngoài check area không được ảnh hưởng phép đo ROI."""
        depth = self.baseline.reference_depth.copy()
        self.analyzer.process(depth)
        clear_output = self.analyzer.process(depth)

        check_area = clear_output.check_area_mask > 0
        roi = self.baseline.roi.to_mask(
            self.baseline.frame_width,
            self.baseline.frame_height,
        ) > 0
        self.assertGreater(np.count_nonzero(check_area), np.count_nonzero(roi))

        rows, columns = np.indices(depth.shape)
        pattern = np.where((rows + columns) % 2 == 0, 0.7, -0.7).astype(np.float32)
        depth[~check_area] += pattern[~check_area]
        output = self.analyzer.process(depth)
        self.assertEqual(int(np.count_nonzero(output.changed_mask)), 0)
        self.assertEqual(int(np.count_nonzero(output.changed_mask[~roi])), 0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_change_only_in_padding_does_not_occupy_roi(self) -> None:
        """Đồ vật thay đổi trong padding không được làm ROI báo có vật cản."""
        clear_depth = self.baseline.reference_depth.copy()
        first = self.analyzer.process(clear_depth)
        self.analyzer.process(clear_depth)
        roi = self.baseline.roi.to_mask(
            self.baseline.frame_width,
            self.baseline.frame_height,
        ) > 0
        padding = (first.check_area_mask > 0) & ~roi

        changed_depth = clear_depth.copy()
        changed_depth[padding] -= 0.5
        first_changed = self.analyzer.process(changed_depth)
        second_changed = self.analyzer.process(changed_depth)
        self.assertEqual(int(np.count_nonzero(first_changed.changed_mask)), 0)
        self.assertEqual(int(np.count_nonzero(second_changed.changed_mask)), 0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_world_coordinates_enable_metric_bev_measurements(self) -> None:
        """Baseline có tọa độ thực phải trả các phép đo và mask BEV."""
        world = WorldCoordinates(
            points=np.array(
                [[0.0, 0.0], [1.75, 0.0], [1.75, 4.55], [0.0, 4.55]],
                dtype=np.float32,
            ),
            unit="m",
            origin="P1",
            x_axis="Từ trái sang phải",
            y_axis="Từ trên xuống dưới",
        )
        baseline = replace(
            self.baseline,
            roi=RoiDefinition(
                normalized_points=self.baseline.roi.normalized_points,
                world_coordinates=world,
            ),
        )
        analyzer = WalkwayAnalyzer(baseline, DetectionConfig())

        clear_output = analyzer.process(baseline.reference_depth)
        occupied_depth = baseline.reference_depth.copy()
        occupied_depth[20:40, 30:50] += np.float32(0.5)
        occupied_output = analyzer.process(occupied_depth)

        self.assertGreater(clear_output.snapshot.maximum_passable_width_meters, 1.7)
        self.assertLess(occupied_output.snapshot.maximum_passable_width_meters, 0.8)
        self.assertTrue(occupied_output.snapshot.bottleneck_free_x_ranges_meters)

    # ─────────────────────────────────────────────────────────────────────────

    def test_missing_world_coordinates_fail_fast(self) -> None:
        """Analyzer phải từ chối baseline không có hệ tọa độ mét."""
        with self.assertRaisesRegex(ValueError, "tọa độ thực"):
            WalkwayAnalyzer(
                make_baseline(with_world_coordinates=False),
                DetectionConfig(),
            )

    # ─────────────────────────────────────────────────────────────────────────

    def test_slanted_entrance_and_exit_still_form_a_route(self) -> None:
        """Cạnh vào/ra nghiêng không được bị nhầm thành các hàng Y cực trị."""
        slanted_world = WorldCoordinates(
            points=np.array(
                [[0.0, 0.0], [1.75, -0.5], [1.75, 5.0], [0.0, 4.55]],
                dtype=np.float32,
            ),
            unit="m",
            origin="P1",
            x_axis="Từ trái sang phải",
            y_axis="Từ trên xuống dưới",
        )
        baseline = replace(
            self.baseline,
            roi=RoiDefinition(
                normalized_points=self.baseline.roi.normalized_points,
                world_coordinates=slanted_world,
            ),
        )

        output = WalkwayAnalyzer(baseline, DetectionConfig()).process(
            baseline.reference_depth
        )

        self.assertGreater(output.snapshot.maximum_passable_width_meters, 1.6)

    # ─────────────────────────────────────────────────────────────────────────

    def test_snapshot_is_ready_for_json_serialization(self) -> None:
        """Snapshot public phải mã hóa JSON được mà không chứa numpy hoặc tuple."""
        output = self.analyzer.process(self.baseline.reference_depth)

        payload = output.snapshot.to_dict()
        encoded = json.dumps(payload)

        self.assertIn("maximum_passable_width_meters", encoded)
        self.assertIsInstance(
            payload["bottleneck"]["free_x_ranges_meters"],
            list,
        )


if __name__ == "__main__":
    unittest.main()
