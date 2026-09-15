"""Kiểm thử lưu JSON và REST API cấu hình camera."""

import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from server.app import create_app
from server.models.config import RuntimeConfig
from server.services.camera_connection import CameraConnectionError
from server.services.config_store import ConfigStore
from server.services.snapshot_store import SnapshotStore
from server.settings import ServerSettings


class FakeMonitorService:
    """Monitor giả để test camera API mà không mở thiết bị thật."""

    def __init__(self, settings: ServerSettings):
        """Lưu settings và tạo snapshot store rỗng."""
        self.settings = settings
        self.snapshot_store = SnapshotStore()

    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Không khởi động worker trong kiểm thử API."""

    # ─────────────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Không cần giải phóng worker trong kiểm thử API."""


class FakeCameraConnectionTester:
    """Tester giả có thể cho phép hoặc từ chối nguồn mà không mở camera thật."""

    def __init__(self):
        """Mặc định cho phép mọi kết nối."""
        self.error: str | None = None
        self.registered: list[str] = []
        self.updated: list[tuple[str, str, str]] = []
        self.removed: list[str] = []

    # ─────────────────────────────────────────────────────────────────────────

    def register(self, _path_name: str, _camera) -> None:
        """Đăng ký giả hoặc phát sinh lỗi kết nối theo cấu hình test."""
        if self.error is not None:
            raise CameraConnectionError(self.error)
        self.registered.append(_path_name)

    # ─────────────────────────────────────────────────────────────────────────

    def remove(self, _path_name: str) -> None:
        """Mô phỏng xóa path thành công."""
        self.removed.append(_path_name)

    # ─────────────────────────────────────────────────────────────────────────

    def update(
        self,
        path_name: str,
        source: str,
        previous_source: str,
    ) -> None:
        """Mô phỏng đổi source hoặc phát sinh lỗi kết nối."""
        if self.error is not None:
            raise CameraConnectionError(self.error)
        self.updated.append((path_name, source, previous_source))


class CameraApiTestCase(unittest.TestCase):
    """Xác nhận CRUD, validation và việc lưu nguyên URL camera."""

    def setUp(self) -> None:
        """Tạo application với tệp cấu hình riêng cho từng test."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temporary_directory.name) / "config.json"
        self.connection_tester = FakeCameraConnectionTester()
        settings = ServerSettings(camera_config_path=str(self.config_path))
        application = create_app(
            settings,
            monitor_factory=FakeMonitorService,
            config_store=ConfigStore(self.config_path),
            camera_connection_tester=self.connection_tester,
        )
        self.client_context = TestClient(application)
        self.client = self.client_context.__enter__()

    # ─────────────────────────────────────────────────────────────────────────

    def tearDown(self) -> None:
        """Đóng application và xóa thư mục cấu hình tạm."""
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    # ─────────────────────────────────────────────────────────────────────────

    def test_create_persists_full_rtsp_url(self) -> None:
        """POST chỉ cần tên và URL rồi lưu nguyên URL vào JSON."""
        source = "rtsp://admin:p%40ss@192.168.1.10:554/stream"
        response = self.client.post(
            "/api/cameras",
            json={"name": "Camera cổng chính", "source": source},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["source"], source)

        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["camera"]["source"], source)
        self.assertEqual(saved["baselines"], [])
        self.assertEqual(
            saved["runtime"],
            RuntimeConfig().model_dump(mode="json"),
        )
        self.assertEqual(set(saved["camera"]), {
            "name",
            "source",
            "open_timeout_ms",
            "read_timeout_ms",
            "id",
            "created_at",
            "updated_at",
        })

    # ─────────────────────────────────────────────────────────────────────────

    def test_new_camera_replaces_current_camera(self) -> None:
        """POST lần hai phải ghi đè JSON và dọn path MediaMTX cũ."""
        first = self.client.post(
            "/api/cameras",
            json={"name": "Camera 1", "source": "rtsp://camera-1/stream"},
        ).json()
        second = self.client.post(
            "/api/cameras",
            json={"name": "Camera 2", "source": "rtsp://camera-2/stream"},
        ).json()

        cameras = self.client.get("/api/cameras").json()
        self.assertEqual(len(cameras), 1)
        self.assertEqual(cameras[0]["id"], second["id"])
        self.assertEqual(self.client.get(f"/api/cameras/{first['id']}").status_code, 404)
        self.assertIn(first["id"], self.connection_tester.removed)

        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["camera"]["id"], second["id"])

    # ─────────────────────────────────────────────────────────────────────────

    def test_camera_update_preserves_baselines_in_shared_config(self) -> None:
        """Cập nhật camera không được ghi đè danh sách baseline cùng tệp."""
        created = self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        ).json()
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["baselines"] = [
            {
                "id": "baseline-01",
                "name": "Baseline kiểm thử",
                "camera_id": created["id"],
                "roi_points": [[0.1, 0.1], [0.9, 0.1], [0.8, 0.9], [0.2, 0.9]],
                "world_points": [[0, 0], [2, 0], [2, 6], [0, 6]],
                "unit": "m",
                "origin": "P1",
                "x_axis": "P1 → P2",
                "y_axis": "P1 → P4",
                "encoder": "vits",
                "frame_count": 60,
                "input_size": 518,
                "process_width": 960,
                "created_at": "2026-09-14T08:00:00Z",
                "updated_at": "2026-09-14T08:00:00Z",
            }
        ]
        self.config_path.write_text(
            json.dumps(config, ensure_ascii=False),
            encoding="utf-8",
        )

        response = self.client.patch(
            f"/api/cameras/{created['id']}",
            json={"name": "Camera đã đổi tên"},
        )

        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved["camera"]["name"], "Camera đã đổi tên")
        self.assertEqual(saved["baselines"][0]["id"], "baseline-01")

    # ─────────────────────────────────────────────────────────────────────────

    def test_source_update_is_applied_to_mediamtx_before_json(self) -> None:
        """PATCH source phải đồng bộ MediaMTX và chỉ sau đó mới lưu JSON."""
        created = self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://old/stream"},
        ).json()

        response = self.client.patch(
            f"/api/cameras/{created['id']}",
            json={"source": "rtsp://new/stream"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "rtsp://new/stream")
        self.assertEqual(
            self.connection_tester.updated,
            [(created["id"], "rtsp://new/stream", "rtsp://old/stream")],
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_source_update_failure_preserves_json(self) -> None:
        """Source mới không kết nối được phải giữ nguyên camera đã lưu."""
        created = self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://old/stream"},
        ).json()
        self.connection_tester.error = "MediaMTX không nhận được luồng camera."

        response = self.client.patch(
            f"/api/cameras/{created['id']}",
            json={"source": "rtsp://offline/stream"},
        )

        self.assertEqual(response.status_code, 422)
        stored = self.client.get(f"/api/cameras/{created['id']}").json()
        self.assertEqual(stored["source"], "rtsp://old/stream")

    # ─────────────────────────────────────────────────────────────────────────

    def test_list_update_and_delete_camera(self) -> None:
        """Camera đã tạo phải đọc, đổi tên và xóa được."""
        created = self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        ).json()
        camera_id = created["id"]

        listed = self.client.get("/api/cameras").json()
        self.assertEqual([camera["id"] for camera in listed], [camera_id])

        updated = self.client.patch(
            f"/api/cameras/{camera_id}",
            json={"name": "Camera hành lang"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Camera hành lang")

        deleted = self.client.delete(f"/api/cameras/{camera_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/cameras").json(), [])

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_invalid_url(self) -> None:
        """Nguồn không phải RTSP hoặc RTMP phải bị từ chối."""
        response = self.client.post(
            "/api/cameras",
            json={"name": "Camera lỗi", "source": "http://camera.local"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.config_path.exists())

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_invalid_url_before_updating_mediamtx(self) -> None:
        """PATCH URL sai phải bị Pydantic chặn trước khi gọi MediaMTX."""
        created = self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://old/stream"},
        ).json()

        response = self.client.patch(
            f"/api/cameras/{created['id']}",
            json={"source": "https://invalid.example/stream"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.connection_tester.updated, [])

    # ─────────────────────────────────────────────────────────────────────────

    def test_returns_not_found_for_unknown_camera(self) -> None:
        """Các thao tác theo ID không tồn tại phải trả HTTP 404."""
        self.assertEqual(self.client.get("/api/cameras/unknown").status_code, 404)
        self.assertEqual(
            self.client.patch(
                "/api/cameras/unknown",
                json={"name": "Camera"},
            ).status_code,
            404,
        )
        self.assertEqual(self.client.delete("/api/cameras/unknown").status_code, 404)

    # ─────────────────────────────────────────────────────────────────────────

    def test_does_not_save_camera_when_connection_fails(self) -> None:
        """POST thất bại kết nối phải trả 422 và không tạo tệp JSON."""
        self.connection_tester.error = "MediaMTX không nhận được luồng camera."

        response = self.client.post(
            "/api/cameras",
            json={"name": "Camera offline", "source": "rtsp://offline/stream"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.config_path.exists())


if __name__ == "__main__":
    unittest.main()
