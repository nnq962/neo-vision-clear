"""Kiểm thử lifespan, health-check và WebSocket bằng monitor giả."""

import unittest

from fastapi.testclient import TestClient

from server.app import create_app
from server.services.snapshot_store import SnapshotStore
from server.settings import ServerSettings
from walkway_monitor.detection.models import CorridorSnapshot


class FakeMonitorService:
    """Monitor không mở camera, dùng để xác nhận vòng đời FastAPI."""

    def __init__(self, settings: ServerSettings, publish_on_start: bool = True):
        """Tạo store rỗng và lưu lựa chọn công bố snapshot khi startup."""
        self.settings = settings
        self.snapshot_store = SnapshotStore()
        self.publish_on_start = publish_on_start
        self.started = False
        self.stopped = False

    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Đánh dấu startup và tùy chọn công bố một snapshot cố định."""
        self.started = True
        if self.publish_on_start:
            self.snapshot_store.publish(
                CorridorSnapshot(
                    maximum_passable_width_meters=0.82,
                    walkway_width_meters=1.75,
                    bottleneck_y_meters=2.35,
                    bottleneck_free_x_ranges_meters=((0.0, 0.82),),
                    frame_index=12,
                    captured_at=1234.5,
                )
            )

    # ─────────────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Đánh dấu shutdown để test xác nhận lifespan đã cleanup."""
        self.stopped = True


class ServerAppTestCase(unittest.TestCase):
    """Kiểm tra tài nguyên lifespan và protocol request-response."""

    def setUp(self) -> None:
        """Tạo settings không phụ thuộc camera hoặc file thật."""
        self.settings = ServerSettings(snapshot_max_age_seconds=5.0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_lifespan_starts_and_stops_monitor(self) -> None:
        """Context TestClient phải sở hữu toàn bộ vòng đời monitor service."""
        services: list[FakeMonitorService] = []

        def factory(settings: ServerSettings) -> FakeMonitorService:
            """Tạo monitor giả và lưu instance để kiểm tra sau shutdown."""
            service = FakeMonitorService(settings)
            services.append(service)
            return service

        application = create_app(self.settings, monitor_factory=factory)
        with TestClient(application) as client:
            self.assertTrue(services[0].started)
            self.assertEqual(client.get("/health").json()["status"], "ok")
        self.assertTrue(services[0].stopped)

    # ─────────────────────────────────────────────────────────────────────────

    def test_websocket_returns_correlated_snapshot(self) -> None:
        """WebSocket phải giữ request_id và trả đầy đủ phép đo mới nhất."""
        application = create_app(
            self.settings,
            monitor_factory=lambda settings: FakeMonitorService(settings),
        )

        # Gửi request hợp lệ trên một kết nối có lifespan đang hoạt động.
        with TestClient(application) as client:
            with client.websocket_connect("/ws/corridor") as websocket:
                websocket.send_json(
                    {"type": "get_corridor_info", "request_id": "req-01"}
                )
                response = websocket.receive_json()

        self.assertEqual(response["type"], "corridor_info")
        self.assertEqual(response["request_id"], "req-01")
        self.assertEqual(response["status"], "ok")
        self.assertEqual(
            response["data"]["maximum_passable_width_meters"],
            0.82,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_websocket_rejects_invalid_message(self) -> None:
        """Message sai type phải nhận protocol error mà không đóng kết nối."""
        application = create_app(
            self.settings,
            monitor_factory=lambda settings: FakeMonitorService(settings),
        )

        with TestClient(application) as client:
            with client.websocket_connect("/ws/corridor") as websocket:
                websocket.send_json({"type": "unknown", "request_id": "req-02"})
                response = websocket.receive_json()

        self.assertEqual(response["type"], "error")
        self.assertEqual(response["code"], "invalid_message")

    # ─────────────────────────────────────────────────────────────────────────

    def test_websocket_reports_warming_up_without_snapshot(self) -> None:
        """Server chưa có frame phải trả warming_up thay vì số đo giả."""
        application = create_app(
            self.settings,
            monitor_factory=lambda settings: FakeMonitorService(
                settings,
                publish_on_start=False,
            ),
        )

        with TestClient(application) as client:
            with client.websocket_connect("/ws/corridor") as websocket:
                websocket.send_json(
                    {"type": "get_corridor_info", "request_id": "req-03"}
                )
                response = websocket.receive_json()

        self.assertEqual(response["status"], "warming_up")
        self.assertIsNone(response["data"])


if __name__ == "__main__":
    unittest.main()
