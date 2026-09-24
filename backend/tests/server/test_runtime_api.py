"""Kiểm thử REST API và quan hệ dữ liệu của cấu hình runtime."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from server.app import create_app
from server.models.config import RuntimeProcessResponse
from server.services.config_store import ConfigError, ConfigStore
from server.services.snapshot_store import SnapshotRead, SnapshotStore
from server.settings import ServerSettings


class FakeMonitorService:
    """Monitor giả không mở model hoặc camera trong test runtime."""

    def __init__(self, settings: ServerSettings):
        """Lưu settings và tạo snapshot store rỗng."""
        self.settings = settings
        self.snapshot_store = SnapshotStore()
        self.started_with: tuple[object, object, object] | None = None
        self.stop_wait: bool | None = None
        self.process_status = "stopped"

    # ─────────────────────────────────────────────────────────────────────────

    def start(self, camera, baseline, runtime) -> RuntimeProcessResponse:
        """Ghi nhận dependency và mô phỏng worker đang bắt đầu."""
        self.started_with = (camera, baseline, runtime)
        self.process_status = "starting"
        return self.status()

    # ─────────────────────────────────────────────────────────────────────────

    def stop(self, wait: bool = True) -> RuntimeProcessResponse:
        """Ghi nhận kiểu dừng và mô phỏng worker đã dừng."""
        self.stop_wait = wait
        self.process_status = "stopped"
        return self.status()

    # ─────────────────────────────────────────────────────────────────────────

    def status(self) -> RuntimeProcessResponse:
        """Trả trạng thái tiến trình giả phục vụ route status."""
        active_baseline_ids = (
            [baseline.id for baseline in self.started_with[1]]
            if self.started_with is not None and self.process_status != "stopped"
            else []
        )
        return RuntimeProcessResponse(
            status=self.process_status,
            active_baseline_ids=active_baseline_ids,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def read_snapshot(self) -> SnapshotRead:
        """Đọc snapshot giả bằng ngưỡng mặc định của server."""
        return self.snapshot_store.read(self.settings.snapshot_max_age_seconds)


class FakeCameraConnectionTester:
    """Tester camera giả chấp nhận mọi nguồn hợp lệ về schema."""

    def register(self, _path_name: str, _camera) -> None:
        """Bỏ qua đăng ký MediaMTX trong test."""

    # ─────────────────────────────────────────────────────────────────────────

    def remove(self, _path_name: str) -> None:
        """Bỏ qua xóa path MediaMTX trong test."""


class FakeCalibrationService:
    """Calibration service giả chỉ phục vụ cleanup lifespan."""

    def stop(self) -> None:
        """Không có calibration worker thật cần dừng."""

    # ─────────────────────────────────────────────────────────────────────────

    def delete_artifacts(self, _baseline_id: str) -> tuple[Path, ...]:
        """Không có artifact thật cần xóa trong test runtime."""
        return ()


class RuntimeApiTestCase(unittest.TestCase):
    """Xác nhận runtime config được validate và lưu trong config chung."""

    def setUp(self) -> None:
        """Tạo app cùng config JSON tạm cho từng test."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.config_path = root / "config.json"
        application = create_app(
            ServerSettings(camera_config_path=str(self.config_path)),
            monitor_factory=FakeMonitorService,
            config_store=ConfigStore(self.config_path),
            camera_connection_tester=FakeCameraConnectionTester(),
            calibration_service=FakeCalibrationService(),
        )
        self.application = application
        self.client_context = TestClient(application)
        self.client = self.client_context.__enter__()

    # ─────────────────────────────────────────────────────────────────────────

    def tearDown(self) -> None:
        """Đóng app và xóa config tạm."""
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    # ─────────────────────────────────────────────────────────────────────────

    def _create_baseline(self) -> dict[str, object]:
        """Tạo camera và baseline hợp lệ để dùng trong test runtime."""
        camera = self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        ).json()
        response = self.client.post(
            "/api/calibration",
            json={
                "camera_id": camera["id"],
                "name": "Baseline runtime",
                "roi_points": [
                    [0.1, 0.1],
                    [0.9, 0.1],
                    [0.9, 0.9],
                    [0.1, 0.9],
                ],
                "world_points": [[0, 0], [2, 0], [2, 6], [0, 6]],
                "unit": "m",
                "encoder": "vits",
                "frame_count": 60,
                "input_size": 518,
                "process_width": 960,
            },
        )
        return response.json()

    # ─────────────────────────────────────────────────────────────────────────

    def test_returns_complete_default_runtime_without_writing_file(self) -> None:
        """GET khi chưa cấu hình phải trả đủ default nhưng không tạo JSON."""
        response = self.client.get("/api/runtime")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["enabled"])
        self.assertEqual(response.json()["active_baseline_ids"], [])
        self.assertNotIn("inference_batch_size", response.json())
        self.assertEqual(response.json()["detection"]["noise_multiplier"], 6.0)
        self.assertFalse(self.config_path.exists())

    # ─────────────────────────────────────────────────────────────────────────

    def test_saves_runtime_for_an_existing_camera_baseline(self) -> None:
        """PUT phải lưu baseline active cùng toàn bộ tuning detection."""
        baseline = self._create_baseline()
        payload = {
            "enabled": True,
            "active_baseline_ids": [baseline["id"]],
            "snapshot_max_age_seconds": 3.0,
            "log_interval_seconds": 1.0,
            "detection": {
                "noise_multiplier": 7.0,
                "minimum_difference": 0.05,
                "bev_pixels_per_meter": 120.0,
                "morphology_divisor": 180,
                "depth_blur_kernel": 7,
                "check_area_padding": 16,
                "depth_alignment": True,
                "alignment_inlier_ratio": 0.6,
                "display_minimum_area_ratio": 0.002,
            },
        }

        updated = self.client.put("/api/runtime", json=payload)
        loaded = self.client.get("/api/runtime")

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(loaded.json(), payload)
        self.assertEqual(updated.json(), loaded.json())

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_enabled_runtime_without_baseline(self) -> None:
        """Runtime bật nhưng chưa chọn baseline phải bị từ chối."""
        response = self.client.put(
            "/api/runtime",
            json={"enabled": True, "active_baseline_ids": []},
        )

        self.assertEqual(response.status_code, 422)

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_unknown_active_baseline(self) -> None:
        """Runtime không được tham chiếu baseline không tồn tại."""
        response = self.client.put(
            "/api/runtime",
            json={"enabled": False, "active_baseline_ids": ["unknown"]},
        )

        self.assertEqual(response.status_code, 422)

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_removed_batch_size_field(self) -> None:
        """API không còn nhận trường batch size do client tự cung cấp."""
        response = self.client.put(
            "/api/runtime",
            json={"inference_batch_size": 32},
        )

        self.assertEqual(response.status_code, 422)

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_legacy_runtime_document_without_migration(self) -> None:
        """Store báo lỗi rõ ràng khi JSON còn schema runtime cũ."""
        # Bước 1: mô phỏng tài liệu cũ mà không gọi endpoint để tránh lỗi 500.
        self.config_path.write_text(
            json.dumps({"version": 2, "runtime": {"inference_batch_size": 2}}),
            encoding="utf-8",
        )

        # Bước 2: schema mới từ chối trường cũ và giữ nguyên file gốc.
        with self.assertRaises(ConfigError):
            self.application.state.config_store.get_runtime()
        self.assertIn("inference_batch_size", self.config_path.read_text(encoding="utf-8"))

    # ─────────────────────────────────────────────────────────────────────────

    def test_deleting_selected_camera_removes_active_baseline(self) -> None:
        """Xóa camera active phải loại baseline khỏi runtime đã lưu."""
        baseline = self._create_baseline()
        self.client.put(
            "/api/runtime",
            json={"active_baseline_ids": [baseline["id"]]},
        )

        deleted = self.client.delete(f"/api/cameras/{baseline['camera_id']}")
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))

        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(persisted["runtime"]["active_baseline_ids"], [])
        self.assertNotIn("inference_batch_size", persisted["runtime"])

    # ─────────────────────────────────────────────────────────────────────────

    def test_deleting_selected_baseline_updates_active_ids(self) -> None:
        """Xóa baseline active phải loại ID khỏi runtime đã lưu."""
        baseline = self._create_baseline()
        self.client.put(
            "/api/runtime",
            json={"active_baseline_ids": [baseline["id"]]},
        )

        deleted = self.client.delete(f"/api/calibration/{baseline['id']}")
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))

        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(persisted["runtime"]["active_baseline_ids"], [])
        self.assertNotIn("inference_batch_size", persisted["runtime"])

    # ─────────────────────────────────────────────────────────────────────────

    def test_start_resolves_camera_from_selected_baseline(self) -> None:
        """Runtime mở camera sở hữu baseline thay vì luôn lấy camera đầu tiên."""
        self.client.post(
            "/api/cameras",
            json={"name": "Camera 1", "source": "rtsp://camera-1/stream"},
        )
        second_camera = self.client.post(
            "/api/cameras",
            json={"name": "Camera 2", "source": "rtsp://camera-2/stream"},
        ).json()
        baseline = self.client.post(
            "/api/calibration",
            json={
                "camera_id": second_camera["id"],
                "name": "Baseline camera 2",
                "roi_points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
                "world_points": [[0, 0], [2, 0], [2, 6], [0, 6]],
            },
        ).json()
        self.client.put(
            "/api/runtime",
            json={"active_baseline_ids": [baseline["id"]]},
        )

        response = self.client.post("/api/runtime/start")

        self.assertEqual(response.status_code, 202)
        service = self.application.state.monitor_service
        self.assertEqual(service.started_with[0][0].id, second_camera["id"])

    # ─────────────────────────────────────────────────────────────────────────

    def test_starts_and_stops_runtime_without_blocking_api_lifespan(self) -> None:
        """API start/stop điều khiển service và đồng bộ cờ enabled đã lưu."""
        baseline = self._create_baseline()
        configured = self.client.put(
            "/api/runtime",
            json={
                "enabled": False,
                "active_baseline_ids": [baseline["id"]],
            },
        )
        self.assertEqual(configured.status_code, 200)

        started = self.client.post("/api/runtime/start")
        status_response = self.client.get("/api/runtime/status")

        self.assertEqual(started.status_code, 202)
        self.assertEqual(started.json()["status"], "starting")
        self.assertEqual(
            status_response.json()["active_baseline_ids"],
            [baseline["id"]],
        )
        self.assertTrue(self.client.get("/api/runtime").json()["enabled"])

        stopped = self.client.post("/api/runtime/stop")

        self.assertEqual(stopped.status_code, 202)
        self.assertEqual(stopped.json()["status"], "stopped")
        self.assertFalse(self.client.get("/api/runtime").json()["enabled"])
        service = self.application.state.monitor_service
        self.assertFalse(service.stop_wait)

    # ─────────────────────────────────────────────────────────────────────────

    def test_start_requires_an_active_baseline(self) -> None:
        """API start từ chối config chưa chọn baseline mà không gọi worker."""
        response = self.client.post("/api/runtime/start")

        self.assertEqual(response.status_code, 409)
        self.assertIn("active_baseline_ids", response.json()["detail"])

    # ─────────────────────────────────────────────────────────────────────────

    def test_start_resolves_multiple_cameras_in_batch_order(self) -> None:
        """API truyền nhiều camera và baseline vào worker theo thứ tự đã chọn."""
        first_baseline = self._create_baseline()
        second_camera = self.client.post(
            "/api/cameras",
            json={"name": "Camera 2", "source": "rtsp://camera-2/stream"},
        ).json()
        second_baseline = self.client.post(
            "/api/calibration",
            json={
                "camera_id": second_camera["id"],
                "name": "Baseline camera 2",
                "roi_points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
                "world_points": [[0, 0], [2, 0], [2, 6], [0, 6]],
            },
        ).json()
        baseline_ids = [first_baseline["id"], second_baseline["id"]]
        self.client.put(
            "/api/runtime",
            json={
                "active_baseline_ids": baseline_ids,
            },
        )

        response = self.client.post("/api/runtime/start")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.client.get("/api/runtime").json()["active_baseline_ids"], baseline_ids)
        service = self.application.state.monitor_service
        self.assertEqual(
            [camera.id for camera in service.started_with[0]],
            [first_baseline["camera_id"], second_camera["id"]],
        )
        self.assertEqual(
            [baseline.id for baseline in service.started_with[1]],
            baseline_ids,
        )


if __name__ == "__main__":
    unittest.main()
