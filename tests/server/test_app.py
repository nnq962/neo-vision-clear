"""Kiểm thử lifespan, health-check và WebSocket bằng monitor giả."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from server.app import create_app
from server.models.camera import CameraConfig, CameraCreate
from server.services.camera_connection import CameraConnectionError
from server.services.config_store import ConfigStore
from server.services.snapshot_store import SnapshotRead, SnapshotStore
from server.settings import ServerSettings
from walkway_monitor.detection.models import CorridorSnapshot
from walkway_monitor.detection.zones import DifferenceZone


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

    # ─────────────────────────────────────────────────────────────────────────

    def read_snapshot(self) -> SnapshotRead:
        """Đọc snapshot giả bằng ngưỡng cấu hình server của test."""
        # Bước 1: dùng cùng store thật để giữ nguyên hành vi stale và error.
        return self.snapshot_store.read(self.settings.snapshot_max_age_seconds)


class FakeCameraConnectionTester:
    """Ghi nhận thao tác khôi phục camera trong lifespan."""

    def __init__(self, error: CameraConnectionError | None = None):
        """Khởi tạo tester với lỗi tùy chọn cho kịch bản suy giảm."""
        self.error = error
        self.restored: list[tuple[str, CameraConfig]] = []

    # ────────────────────────────────────────────────────────────────────────

    def restore(self, path_name: str, camera: CameraConfig) -> None:
        """Ghi nhận camera và phát sinh lỗi đã cấu hình nếu có."""
        self.restored.append((path_name, camera))
        if self.error is not None:
            raise self.error


class ServerAppTestCase(unittest.TestCase):
    """Kiểm tra tài nguyên lifespan và protocol request-response."""

    def setUp(self) -> None:
        """Tạo settings không phụ thuộc camera hoặc file thật."""
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.config_path = Path(temporary_directory.name) / "config.json"
        self.settings = ServerSettings(
            camera_config_path=str(self.config_path),
            snapshot_max_age_seconds=5.0,
        )

    # ────────────────────────────────────────────────────────────────────────

    def test_lifespan_restores_persisted_camera_path(self) -> None:
        """Startup phải đăng ký lại camera đã lưu vào MediaMTX."""
        store = ConfigStore(self.config_path)
        camera = store.create_camera(
            CameraCreate(name="Camera", source="rtsp://camera/stream"),
            camera_id="camera-01",
        )
        tester = FakeCameraConnectionTester()
        application = create_app(
            self.settings,
            monitor_factory=lambda settings: FakeMonitorService(settings),
            config_store=store,
            camera_connection_tester=tester,
        )

        with TestClient(application) as client:
            self.assertEqual(client.get("/health").status_code, 200)

        self.assertEqual(tester.restored, [(camera.id, camera)])

    # ────────────────────────────────────────────────────────────────────────

    def test_lifespan_stays_available_when_camera_restore_fails(self) -> None:
        """Lỗi MediaMTX khi startup không được làm API ngừng phục vụ."""
        store = ConfigStore(self.config_path)
        store.create_camera(
            CameraCreate(name="Camera", source="rtsp://camera/stream"),
            camera_id="camera-01",
        )
        tester = FakeCameraConnectionTester(
            CameraConnectionError("MediaMTX tạm thời không sẵn sàng.")
        )
        application = create_app(
            self.settings,
            monitor_factory=lambda settings: FakeMonitorService(settings),
            config_store=store,
            camera_connection_tester=tester,
        )

        with TestClient(application) as client:
            self.assertEqual(client.get("/health").status_code, 200)

    # ─────────────────────────────────────────────────────────────────────────

    def test_lifespan_does_not_start_runtime_and_still_stops_service(self) -> None:
        """Lifespan chỉ phục vụ API và vẫn cleanup service khi shutdown."""
        services: list[FakeMonitorService] = []

        def factory(settings: ServerSettings) -> FakeMonitorService:
            """Tạo monitor giả và lưu instance để kiểm tra sau shutdown."""
            service = FakeMonitorService(settings)
            services.append(service)
            return service

        application = create_app(self.settings, monitor_factory=factory)
        with TestClient(application) as client:
            self.assertFalse(services[0].started)
            self.assertEqual(client.get("/health").json()["status"], "warming_up")
        self.assertTrue(services[0].stopped)

    # ─────────────────────────────────────────────────────────────────────────

    def test_websocket_returns_correlated_snapshot(self) -> None:
        """WebSocket phải giữ request_id và trả đầy đủ phép đo mới nhất."""
        def factory(settings: ServerSettings) -> FakeMonitorService:
            """Tạo service có snapshot giả mà không phụ thuộc autostart."""
            service = FakeMonitorService(settings)
            service.snapshot_store.publish(
                CorridorSnapshot(
                    maximum_passable_width_meters=0.82,
                    walkway_width_meters=1.75,
                    bottleneck_y_meters=2.35,
                    bottleneck_free_x_ranges_meters=((0.0, 0.82),),
                    frame_index=12,
                    captured_at=1234.5,
                )
            )
            return service

        application = create_app(
            self.settings,
            monitor_factory=factory,
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

    def test_overview_websocket_returns_difference_zones(self) -> None:
        """WebSocket dashboard phải trả polygon cùng snapshot tương ứng."""
        def factory(settings: ServerSettings) -> FakeMonitorService:
            """Tạo service có một snapshot và một zone chuẩn hóa cố định."""
            service = FakeMonitorService(settings)
            snapshot = CorridorSnapshot(
                maximum_passable_width_meters=0.82,
                walkway_width_meters=1.75,
                bottleneck_y_meters=2.35,
                bottleneck_free_x_ranges_meters=((0.0, 0.82),),
                frame_index=12,
                captured_at=1234.5,
            )
            zone = DifferenceZone(
                polygon=((0.2, 0.3), (0.4, 0.3), (0.4, 0.6)),
                area_ratio=0.04,
            )
            service.snapshot_store.publish(snapshot, (zone,))
            return service

        application = create_app(self.settings, monitor_factory=factory)

        # Gửi message riêng của overview để không thay đổi protocol robot cũ.
        with TestClient(application) as client:
            with client.websocket_connect("/ws/overview") as websocket:
                websocket.send_json(
                    {"type": "get_overview_info", "request_id": "overview-01"}
                )
                response = websocket.receive_json()

        self.assertEqual(response["type"], "overview_info")
        self.assertEqual(response["request_id"], "overview-01")
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["data"]["changed_zones"][0]["area_ratio"], 0.04)
        self.assertEqual(
            response["data"]["changed_zones"][0]["polygon"],
            [[0.2, 0.3], [0.4, 0.3], [0.4, 0.6]],
        )

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
