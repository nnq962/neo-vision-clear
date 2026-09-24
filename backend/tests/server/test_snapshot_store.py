"""Kiểm thử trạng thái tuổi dữ liệu và lỗi của SnapshotStore."""

import unittest
from unittest.mock import patch

from server.services.snapshot_store import SnapshotStore
from walkway_monitor.detection.models import CorridorSnapshot
from walkway_monitor.detection.zones import DifferenceZone


def make_snapshot() -> CorridorSnapshot:
    """Tạo snapshot tối giản dùng chung cho các kiểm thử store."""
    return CorridorSnapshot(
        maximum_passable_width_meters=0.82,
        walkway_width_meters=1.75,
        bottleneck_y_meters=2.35,
        bottleneck_free_x_ranges_meters=((0.0, 0.82),),
        frame_index=1,
        captured_at=1000.0,
    )


class SnapshotStoreTestCase(unittest.TestCase):
    """Kiểm tra store phân loại snapshot stale và lỗi worker chính xác."""

    def test_snapshot_becomes_stale_after_maximum_age(self) -> None:
        """Tuổi vượt ngưỡng phải trả stale nhưng vẫn giữ snapshot cuối."""
        store = SnapshotStore()

        # Cố định monotonic để không phụ thuộc tốc độ máy chạy test.
        with patch("server.services.snapshot_store.time.monotonic", return_value=10.0):
            store.publish(make_snapshot())
        with patch("server.services.snapshot_store.time.monotonic", return_value=12.5):
            reading = store.read(maximum_age_seconds=2.0)

        self.assertEqual(reading.status, "stale")
        self.assertEqual(reading.age_ms, 2500)
        self.assertIsNotNone(reading.snapshot)

    # ─────────────────────────────────────────────────────────────────────────

    def test_worker_error_takes_priority_over_snapshot_age(self) -> None:
        """Lỗi worker phải được báo dù store vẫn còn snapshot trước đó."""
        store = SnapshotStore()
        store.publish(make_snapshot())
        store.set_error("camera disconnected")

        reading = store.read(maximum_age_seconds=2.0)

        self.assertEqual(reading.status, "error")
        self.assertEqual(reading.error, "camera disconnected")

    # ─────────────────────────────────────────────────────────────────────────

    def test_snapshot_and_zones_are_published_and_reset_together(self) -> None:
        """Zone phải đi cùng đúng snapshot và bị xóa khi mở phiên runtime mới."""
        store = SnapshotStore()
        zone = DifferenceZone(
            polygon=((0.1, 0.2), (0.4, 0.2), (0.4, 0.6)),
            area_ratio=0.06,
        )

        # Bước 1: công bố rồi đọc lại cả hai phần trong cùng state của store.
        store.publish(make_snapshot(), (zone,))
        reading = store.read(maximum_age_seconds=2.0)
        self.assertEqual(reading.difference_zones, (zone,))

        # Bước 2: reset không được để zone cũ xuất hiện ở phiên kế tiếp.
        store.reset()
        reset_reading = store.read(maximum_age_seconds=2.0)
        self.assertEqual(reset_reading.status, "warming_up")
        self.assertEqual(reset_reading.difference_zones, ())


if __name__ == "__main__":
    unittest.main()
