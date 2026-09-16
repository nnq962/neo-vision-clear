"""Kiểm thử quy trình đăng ký camera qua MediaMTX."""

from datetime import datetime, timezone
import unittest

from server.models.camera import CameraConfig, CameraCreate
from server.services.camera_connection import (
    CameraConnectionError,
    CameraConnectionTester,
)


class FakeMediaMtxClient:
    """MediaMTX client giả điều khiển trạng thái ready theo từng lần đọc."""

    def __init__(self, ready_states: list[bool]):
        """Khởi tạo chuỗi trạng thái và danh sách path được thao tác."""
        self.ready_states = ready_states
        self.added: list[tuple[str, str]] = []
        self.updated: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    # ─────────────────────────────────────────────────────────────────────────

    def add_source_path(self, path_name: str, source: str) -> None:
        """Ghi nhận path và source được gửi đến MediaMTX."""
        self.added.append((path_name, source))

    # ─────────────────────────────────────────────────────────────────────────

    def get_path(self, _path_name: str) -> dict[str, object] | None:
        """Trả lần lượt trạng thái ready đã cấu hình."""
        ready = self.ready_states.pop(0) if self.ready_states else False
        return {"ready": ready}

    # ─────────────────────────────────────────────────────────────────────────

    def update_source_path(self, path_name: str, source: str) -> None:
        """Ghi nhận lần đổi source hoặc rollback source."""
        self.updated.append((path_name, source))

    # ─────────────────────────────────────────────────────────────────────────

    def delete_path(self, path_name: str, ignore_missing: bool = True) -> None:
        """Ghi nhận path probe đã được cleanup."""
        self.deleted.append(path_name)


class CameraConnectionTesterTestCase(unittest.TestCase):
    """Xác nhận tester gửi nguyên URL, chờ ready và rollback khi lỗi."""

    def setUp(self) -> None:
        """Tạo payload RTSP dùng chung cho từng test."""
        self.source = "rtsp://admin:p%40ss@10.70.22.215:554/stream"
        self.camera = CameraCreate(name="Camera", source=self.source)

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_source_that_never_becomes_ready(self) -> None:
        """Path không ready phải phát sinh lỗi và được rollback khỏi MediaMTX."""
        client = FakeMediaMtxClient([False])
        tester = CameraConnectionTester(
            client=client,
            attempts=1,
            interval_seconds=0,
        )

        with self.assertRaises(CameraConnectionError):
            tester.register("camera-01", self.camera)

        self.assertEqual(client.deleted, ["camera-01"])

    # ─────────────────────────────────────────────────────────────────────────

    def test_register_keeps_ready_path(self) -> None:
        """Đăng ký thành công phải giữ path để frontend xem WebRTC."""
        client = FakeMediaMtxClient([True])
        tester = CameraConnectionTester(
            client=client,
            attempts=1,
            interval_seconds=0,
        )

        tester.register("camera-01", self.camera)

        self.assertEqual(client.added, [("camera-01", self.source)])
        self.assertEqual(client.deleted, [])

    # ─────────────────────────────────────────────────────────────────────────

    def test_restore_replaces_persisted_camera_path(self) -> None:
        """Khôi phục phải xóa path cũ rồi thêm lại source đã lưu."""
        client = FakeMediaMtxClient([])
        tester = CameraConnectionTester(client=client)
        now = datetime.now(timezone.utc)
        camera = CameraConfig(
            id="camera-01",
            name="Camera",
            source=self.source,
            created_at=now,
            updated_at=now,
        )

        tester.restore(camera.id, camera)

        self.assertEqual(client.deleted, ["camera-01"])
        self.assertEqual(client.added, [("camera-01", self.source)])

    # ─────────────────────────────────────────────────────────────────────────

    def test_update_keeps_new_source_when_it_becomes_ready(self) -> None:
        """Source mới ready phải được giữ lại mà không rollback."""
        client = FakeMediaMtxClient([True])
        tester = CameraConnectionTester(
            client=client,
            attempts=1,
            interval_seconds=0,
        )

        tester.update("camera-01", "rtsp://new/stream", self.source)

        self.assertEqual(client.updated, [("camera-01", "rtsp://new/stream")])

    # ─────────────────────────────────────────────────────────────────────────

    def test_update_restores_previous_source_when_not_ready(self) -> None:
        """Source mới lỗi phải đưa cấu hình MediaMTX trở về source trước đó."""
        client = FakeMediaMtxClient([False])
        tester = CameraConnectionTester(
            client=client,
            attempts=1,
            interval_seconds=0,
        )

        with self.assertRaises(CameraConnectionError):
            tester.update("camera-01", "rtsp://offline/stream", self.source)

        self.assertEqual(
            client.updated,
            [
                ("camera-01", "rtsp://offline/stream"),
                ("camera-01", self.source),
            ],
        )


if __name__ == "__main__":
    unittest.main()
