"""Kiểm thử quy trình xác nhận camera qua MediaMTX path tạm."""

import unittest

from server.models.camera import CameraCreate
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

    def delete_path(self, path_name: str, ignore_missing: bool = True) -> None:
        """Ghi nhận path probe đã được cleanup."""
        self.deleted.append(path_name)


class CameraConnectionTesterTestCase(unittest.TestCase):
    """Xác nhận tester gửi nguyên URL, chờ ready và luôn cleanup."""

    def setUp(self) -> None:
        """Tạo payload RTSP dùng chung cho từng test."""
        self.source = "rtsp://admin:p%40ss@10.70.22.215:554/stream"
        self.camera = CameraCreate(name="Camera", source=self.source)

    # ─────────────────────────────────────────────────────────────────────────

    def test_waits_until_path_is_ready_and_removes_probe(self) -> None:
        """Tester phải chờ ready, giữ nguyên URL và cleanup path."""
        client = FakeMediaMtxClient([False, True])
        tester = CameraConnectionTester(
            client=client,
            attempts=2,
            interval_seconds=0,
        )

        tester.validate(self.camera)

        path_name, runtime_source = client.added[0]
        self.assertEqual(runtime_source, self.source)
        self.assertEqual(client.deleted, [path_name])

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_source_that_never_becomes_ready(self) -> None:
        """Path không ready phải phát sinh lỗi và vẫn được xóa khỏi MediaMTX."""
        client = FakeMediaMtxClient([False])
        tester = CameraConnectionTester(
            client=client,
            attempts=1,
            interval_seconds=0,
        )

        with self.assertRaises(CameraConnectionError):
            tester.validate(self.camera)

        self.assertEqual(client.deleted, [client.added[0][0]])

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


if __name__ == "__main__":
    unittest.main()
