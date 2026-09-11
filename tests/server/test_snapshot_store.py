"""Kiểm thử trạng thái tuổi dữ liệu và lỗi của SnapshotStore."""

import unittest
from unittest.mock import patch

from server.services.snapshot_store import SnapshotStore
from walkway_monitor.detection.models import CorridorSnapshot


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


if __name__ == "__main__":
    unittest.main()
