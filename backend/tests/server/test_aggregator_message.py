"""Kiểm thử payload một chiều từ backend Jetson tới Aggregator."""

from datetime import datetime, timezone
import unittest

from server.models.aggregator import CameraMeasurementMessage
from server.models.camera import CameraConfig
from walkway_monitor.detection.models import (
    ClearanceZone,
    CorridorSnapshot,
    ZoneClearance,
)


class CameraMeasurementMessageTestCase(unittest.TestCase):
    """Xác nhận snapshot nội bộ được rút gọn đúng schema đã chốt."""

    def setUp(self) -> None:
        """Tạo camera cố định dùng chung cho các phép chuyển đổi."""
        timestamp = datetime.now(timezone.utc)
        self.camera = CameraConfig(
            id="camera-03",
            name="Camera 3",
            source="rtsp://camera.local/stream",
            created_at=timestamp,
            updated_at=timestamp,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_blocked_snapshot_becomes_compact_message(self) -> None:
        """Payload giữ camera, zone và độ rộng nhưng loại frame_index."""
        snapshot = CorridorSnapshot(
            maximum_passable_width_meters=0.18,
            walkway_width_meters=1.0,
            bottleneck_y_meters=2.0,
            bottleneck_free_x_ranges_meters=((0.0, 0.18),),
            frame_index=99,
            captured_at=1_797_000_000.0,
            zone_clearance=ZoneClearance(
                zones=tuple(
                    ClearanceZone(
                        index=index,
                        name=f"zone_{index}",
                        start_ratio=(index - 1) / 10,
                        end_ratio=index / 10,
                        free_ratio=0.18 if index in (4, 5) else 0.8,
                        occupancy_ratio=0.82 if index in (4, 5) else 0.2,
                        blocked=index in (4, 5),
                    )
                    for index in range(1, 11)
                ),
                minimum_free_ratio=0.18,
                minimum_required_ratio=0.4,
                blocked_zone_indices=(4, 5),
                can_pass=False,
            ),
        )

        message = CameraMeasurementMessage.from_snapshot(self.camera, snapshot)
        payload = message.model_dump(mode="json", exclude_none=True)

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["camera_id"], "camera-03")
        self.assertEqual(payload["camera_name"], "Camera 3")
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["blocked_zones"], [4, 5])
        self.assertEqual(payload["zone_count"], 10)
        self.assertEqual(payload["max_passable_width_cm"], 18.0)
        self.assertEqual(payload["reason"], "insufficient_clearance")
        self.assertNotIn("frame_index", payload)


if __name__ == "__main__":
    unittest.main()
