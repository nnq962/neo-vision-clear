"""Kiểm thử phép đo bề rộng tuyến liên thông trên BEV."""

import unittest

import numpy as np

from walkway_monitor.detection.components import measure_route_capacity


class RouteCapacityTestCase(unittest.TestCase):
    """Kiểm tra bề rộng footprint có thể đi từ đầu đến cuối hành lang."""

    def test_center_obstacle_keeps_two_side_routes(self) -> None:
        """Vật ở giữa phải để lại hai tuyến độc lập rộng đúng 0.8 mét."""
        roi = np.full((30, 20), 255, dtype=np.uint8)
        obstacle = np.zeros_like(roi)
        obstacle[:, 8:12] = 255
        entrance, exit_mask = self._horizontal_boundaries(roi)

        capacity = measure_route_capacity(
            obstacle,
            roi,
            entrance,
            exit_mask,
            pixels_per_meter=10.0,
            minimum_world_x=0.0,
            minimum_world_y=-0.5,
        )

        self.assertAlmostEqual(capacity.maximum_passable_width_meters, 0.8)
        self.assertAlmostEqual(capacity.walkway_width_meters, 2.0)
        self.assertAlmostEqual(capacity.bottleneck_y_meters, 1.0)
        self.assertEqual(
            capacity.bottleneck_free_x_ranges_meters,
            ((0.0, 0.8), (1.2, 2.0)),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_staggered_obstacles_measure_connected_route(self) -> None:
        """Vật xen kẽ phải giới hạn tuyến theo vùng giao nhau giữa hai phía."""
        roi = np.full((30, 30), 255, dtype=np.uint8)
        obstacle = np.zeros_like(roi)
        obstacle[:15, 18:] = 255
        obstacle[15:, :12] = 255
        entrance, exit_mask = self._horizontal_boundaries(roi)

        capacity = measure_route_capacity(
            obstacle,
            roi,
            entrance,
            exit_mask,
            pixels_per_meter=10.0,
            minimum_world_x=0.0,
            minimum_world_y=0.0,
        )

        # Từng nửa có khoảng trống 1.8 m, nhưng chỉ 0.6 m nối xuyên suốt.
        self.assertAlmostEqual(capacity.maximum_passable_width_meters, 0.6)

    # ─────────────────────────────────────────────────────────────────────────

    def test_wall_across_corridor_reports_zero(self) -> None:
        """Một vách chắn ngang toàn hành lang phải làm tuyến liên thông bằng 0."""
        roi = np.full((30, 20), 255, dtype=np.uint8)
        obstacle = np.zeros_like(roi)
        obstacle[14:16, :] = 255
        entrance, exit_mask = self._horizontal_boundaries(roi)

        capacity = measure_route_capacity(
            obstacle,
            roi,
            entrance,
            exit_mask,
            pixels_per_meter=10.0,
            minimum_world_x=-1.0,
            minimum_world_y=-0.5,
        )

        self.assertEqual(capacity.maximum_passable_width_meters, 0.0)
        self.assertAlmostEqual(capacity.bottleneck_y_meters, 1.0)
        self.assertEqual(capacity.bottleneck_free_x_ranges_meters, ())

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _horizontal_boundaries(
        roi: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Tạo mask cạnh vào ở hàng đầu và cạnh ra ở hàng cuối của ROI chữ nhật."""
        entrance = np.zeros_like(roi)
        exit_mask = np.zeros_like(roi)
        entrance[0] = roi[0]
        exit_mask[-1] = roi[-1]
        return entrance, exit_mask


if __name__ == "__main__":
    unittest.main()
