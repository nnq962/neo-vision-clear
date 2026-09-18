"""Kiểm thử REST API lưu cấu hình calibration mà không chạy pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from server.app import create_app
from server.models.calibration import CalibrationRunResponse
from server.services.config_store import ConfigStore
from server.services.snapshot_store import SnapshotStore
from server.settings import ServerSettings


class FakeMonitorService:
    """Monitor giả bảo đảm test không mở camera hay pipeline xử lý."""

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
    """Tester camera giả không thực hiện kết nối mạng."""

    def register(self, _path_name: str, _camera) -> None:
        """Chấp nhận camera mà không đăng ký MediaMTX thật."""

    # ─────────────────────────────────────────────────────────────────────────

    def remove(self, _path_name: str) -> None:
        """Bỏ qua thao tác xóa MediaMTX trong test."""


class FakeCalibrationService:
    """Service giả xác nhận route run/status mà không nạp model."""

    def __init__(self):
        """Khởi tạo danh sách baseline đã được yêu cầu chạy."""
        self.started: list[str] = []
        self.deleted: list[str] = []
        self.image_path: Path | None = None

    # ─────────────────────────────────────────────────────────────────────────

    def start(self, baseline_id: str) -> CalibrationRunResponse:
        """Ghi nhận baseline và trả trạng thái running."""
        self.started.append(baseline_id)
        return CalibrationRunResponse(
            baseline_id=baseline_id,
            status="running",
            total_frames=60,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def status(self, baseline_id: str) -> CalibrationRunResponse:
        """Trả tiến độ giả để kiểm tra endpoint trạng thái."""
        return CalibrationRunResponse(
            baseline_id=baseline_id,
            status="running",
            processed_frames=12,
            total_frames=60,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Không có worker thật cần dừng trong test."""

    # ─────────────────────────────────────────────────────────────────────────

    def delete_artifacts(self, baseline_id: str) -> tuple[Path, ...]:
        """Ghi nhận yêu cầu xóa artifact mà không thao tác filesystem."""
        self.deleted.append(baseline_id)
        return ()

    # ─────────────────────────────────────────────────────────────────────────

    def get_artifact_image_path(
        self,
        _baseline_id: str,
        _image_type: str,
    ) -> Path:
        """Trả ảnh giả đã được test case chuẩn bị."""
        if self.image_path is None:
            raise FileNotFoundError("Ảnh giả chưa được cấu hình.")
        return self.image_path


class CalibrationApiTestCase(unittest.TestCase):
    """Xác nhận API quản lý nhiều baseline trong config chung."""

    def setUp(self) -> None:
        """Tạo application và các tệp JSON riêng cho từng test."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_path = Path(self.temporary_directory.name)
        self.camera_path = temporary_path / "camera.json"
        self.calibration_path = temporary_path / "calibration.json"
        settings = ServerSettings(
            camera_config_path=str(self.camera_path),
        )
        self.calibration_service = FakeCalibrationService()
        application = create_app(
            settings,
            monitor_factory=FakeMonitorService,
            config_store=ConfigStore(
                self.camera_path,
                legacy_calibration_path=self.calibration_path,
            ),
            camera_connection_tester=FakeCameraConnectionTester(),
            calibration_service=self.calibration_service,
        )
        self.client_context = TestClient(application)
        self.client = self.client_context.__enter__()
        self.payload = {
            "name": "Giờ làm việc",
            "roi_points": [[0.1, 0.1], [0.9, 0.1], [0.8, 0.9], [0.2, 0.9]],
            "world_points": [[0.0, 0.0], [2.0, 0.0], [2.0, 6.0], [0.0, 6.0]],
            "unit": "m",
            "encoder": "vits",
            "frame_count": 60,
            "input_size": 518,
            "process_width": 960,
        }

    # ─────────────────────────────────────────────────────────────────────────

    def tearDown(self) -> None:
        """Đóng application và xóa dữ liệu tạm."""
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    # ─────────────────────────────────────────────────────────────────────────

    def test_returns_empty_list_before_configuration_exists(self) -> None:
        """GET trả danh sách rỗng khi chưa lưu và không tạo tệp."""
        response = self.client.get("/api/calibration")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        self.assertFalse(self.camera_path.exists())

    # ─────────────────────────────────────────────────────────────────────────

    def test_requires_a_saved_camera(self) -> None:
        """POST từ chối cấu hình khi backend chưa có camera hiện tại."""
        response = self.client.post("/api/calibration", json=self.payload)

        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.camera_path.exists())

    # ─────────────────────────────────────────────────────────────────────────

    def test_saves_multiple_baselines_without_running_pipeline(self) -> None:
        """POST thêm nhiều baseline và liên kết chúng với camera singleton."""
        camera = self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        ).json()

        first = self.client.post("/api/calibration", json=self.payload)
        changed_payload = {
            **self.payload,
            "name": "Ngoài giờ",
            "frame_count": 90,
        }
        second = self.client.post("/api/calibration", json=changed_payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.json()["camera_id"], camera["id"])
        self.assertEqual(second.json()["frame_count"], 90)
        self.assertNotEqual(second.json()["id"], first.json()["id"])

        listed = self.client.get("/api/calibration").json()
        self.assertEqual([item["name"] for item in listed], ["Ngoài giờ", "Giờ làm việc"])

        saved = json.loads(self.camera_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["version"], 2)
        self.assertEqual(len(saved["baselines"]), 2)
        self.assertEqual(saved["baselines"][1]["frame_count"], 90)
        self.assertNotIn("status", saved["baselines"][1])

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_duplicate_name_for_the_same_camera(self) -> None:
        """POST từ chối tên trùng dù khác hoa thường hoặc có khoảng trắng."""
        self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        )
        first = self.client.post("/api/calibration", json=self.payload)

        duplicate = self.client.post(
            "/api/calibration",
            json={**self.payload, "name": "  GIỜ LÀM VIỆC  "},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("đã tồn tại", duplicate.json()["detail"])
        self.assertEqual(len(self.client.get("/api/calibration").json()), 1)

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_duplicate_name_when_updating(self) -> None:
        """PUT không được đổi một baseline thành tên của baseline cùng camera."""
        self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        )
        first = self.client.post("/api/calibration", json=self.payload).json()
        second = self.client.post(
            "/api/calibration",
            json={**self.payload, "name": "Ngoài giờ"},
        ).json()

        duplicate = self.client.put(
            f"/api/calibration/{second['id']}",
            json={**self.payload, "name": first["name"].upper()},
        )

        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            self.client.get(f"/api/calibration/{second['id']}").json()["name"],
            "Ngoài giờ",
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_reads_updates_and_deletes_one_baseline(self) -> None:
        """API theo ID chỉ thay đổi baseline được chỉ định."""
        self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        )
        created = self.client.post("/api/calibration", json=self.payload).json()
        baseline_id = created["id"]

        fetched = self.client.get(f"/api/calibration/{baseline_id}")
        updated = self.client.put(
            f"/api/calibration/{baseline_id}",
            json={**self.payload, "name": "Baseline đã đổi tên"},
        )
        deleted = self.client.delete(f"/api/calibration/{baseline_id}")

        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Baseline đã đổi tên")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/calibration").json(), [])
        self.assertEqual(
            self.client.get(f"/api/calibration/{baseline_id}").status_code,
            404,
        )
        self.assertEqual(self.calibration_service.deleted, [baseline_id])

    # ─────────────────────────────────────────────────────────────────────────

    def test_starts_calibration_and_reads_progress(self) -> None:
        """Route run trả 202 và status công bố tiến độ service."""
        self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        )
        baseline = self.client.post("/api/calibration", json=self.payload).json()

        started = self.client.post(f"/api/calibration/{baseline['id']}/run")
        progress = self.client.get(f"/api/calibration/{baseline['id']}/status")

        self.assertEqual(started.status_code, 202)
        self.assertEqual(started.json()["status"], "running")
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(progress.json()["processed_frames"], 12)
        self.assertEqual(self.calibration_service.started, [baseline["id"]])

    # ─────────────────────────────────────────────────────────────────────────

    def test_gets_preview_image_for_one_baseline(self) -> None:
        """Endpoint ảnh phải trả đúng JPEG của baseline được yêu cầu."""
        self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        )
        baseline = self.client.post("/api/calibration", json=self.payload).json()
        image_path = self.camera_path.parent / "preview.jpg"
        image_path.write_bytes(b"fake-jpeg")
        self.calibration_service.image_path = image_path

        response = self.client.get(
            f"/api/calibration/{baseline['id']}/images/preview"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(response.content, b"fake-jpeg")

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_invalid_roi(self) -> None:
        """POST từ chối ROI ngoài miền chuẩn hóa hoặc không đủ bốn điểm."""
        self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        )
        invalid_payload = {**self.payload, "roi_points": [[0.0, 0.0]] * 4}

        response = self.client.post("/api/calibration", json=invalid_payload)

        self.assertEqual(response.status_code, 422)
        saved = json.loads(self.camera_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["baselines"], [])

    # ─────────────────────────────────────────────────────────────────────────

    def test_reads_legacy_single_calibration_as_a_list(self) -> None:
        """Store giữ lại cấu hình singleton phiên bản 1 khi nâng schema."""
        camera = self.client.post(
            "/api/cameras",
            json={"name": "Camera", "source": "rtsp://camera.local/stream"},
        ).json()
        # Mô phỏng config camera phiên bản cũ chưa có trường baselines.
        unified = json.loads(self.camera_path.read_text(encoding="utf-8"))
        self.camera_path.write_text(
            json.dumps(
                {"version": 1, "camera": unified["camera"]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        legacy = {
            "version": 1,
            "calibration": {
                "camera_id": camera["id"],
                "roi_points": self.payload["roi_points"],
                "world_points": self.payload["world_points"],
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
            },
        }
        self.calibration_path.write_text(
            json.dumps(legacy, ensure_ascii=False),
            encoding="utf-8",
        )

        response = self.client.get("/api/calibration")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["id"], "legacy-baseline")
        self.assertEqual(response.json()[0]["name"], "Baseline đã lưu")

        # Lần đọc đầu tiên đã hợp nhất dữ liệu cũ vào config chính.
        migrated = json.loads(self.camera_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["version"], 2)
        self.assertEqual(migrated["baselines"][0]["id"], "legacy-baseline")

        # Các mutation tiếp theo chỉ làm việc trên config chung.
        updated_payload = {**self.payload, "name": "Baseline đã nhập"}
        updated = self.client.put(
            "/api/calibration/legacy-baseline",
            json=updated_payload,
        )
        saved = json.loads(self.camera_path.read_text(encoding="utf-8"))
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["baselines"][0]["name"], "Baseline đã nhập")


if __name__ == "__main__":
    unittest.main()
