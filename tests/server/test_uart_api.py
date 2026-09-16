"""Kiểm thử UART FastAPI không làm gián đoạn server khi serial lỗi."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from server.app import create_app
from server.models.uart import UartConfig
from server.services.config_store import ConfigStore
from server.services.snapshot_store import SnapshotRead, SnapshotStore
from server.services.uart import UartService
from server.settings import ServerSettings
from uart.messages import CorridorInfo, GetCorridorInfo, MessageBase, MessageType


class FakeMonitorService:
    """Monitor tối thiểu để lifespan và health route hoạt động trong test."""

    def __init__(self, settings: ServerSettings):
        """Khởi tạo snapshot store rỗng và giữ settings."""
        self.settings = settings
        self.snapshot_store = SnapshotStore()

    # ─────────────────────────────────────────────────────────────────────────

    def read_snapshot(self) -> SnapshotRead:
        """Trả trạng thái warming-up khi test chưa công bố snapshot."""
        return self.snapshot_store.read(2.0)

    # ─────────────────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Cho phép lifespan cleanup mà không tạo worker thật."""


class FakeUartManager:
    """UART manager giả cho phép một port thành công và port khác thất bại."""

    def __init__(self) -> None:
        """Khởi tạo manager ở trạng thái đóng và chưa có handler."""
        self.port = "/dev/missing"
        self.baudrate = 115200
        self.timeout = 1.0
        self.connected = False
        self.is_listening = False
        self.last_error: str | None = None
        self.sent: list[MessageBase] = []
        self.handlers: dict[int, object] = {}
        self.generic_handler = None

    # ─────────────────────────────────────────────────────────────────────────

    def set_handler(self, message_type: int, handler: object) -> None:
        """Lưu handler theo message type để test có thể phát request."""
        self.handlers[int(message_type)] = handler

    # ─────────────────────────────────────────────────────────────────────────

    def set_generic_handler(self, handler: object) -> None:
        """Lưu generic handler tương tự manager thật."""
        self.generic_handler = handler

    # ─────────────────────────────────────────────────────────────────────────

    def configure(self, port: str, baudrate: int, timeout: float) -> bool:
        """Áp dụng cấu hình mà chưa kết nối."""
        changed = (port, baudrate, timeout) != (
            self.port,
            self.baudrate,
            self.timeout,
        )
        self.port, self.baudrate, self.timeout = port, baudrate, timeout
        return changed

    # ─────────────────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Chỉ cho cổng /dev/ttyOK kết nối thành công."""
        self.connected = self.port == "/dev/ttyOK"
        self.is_listening = self.connected
        self.last_error = None if self.connected else f"Không mở được {self.port}."
        return self.connected

    # ─────────────────────────────────────────────────────────────────────────

    def reconfigure(self, port: str, baudrate: int, timeout: float) -> bool:
        """Áp dụng cấu hình rồi thử kết nối như manager thật."""
        self.configure(port, baudrate, timeout)
        return self.connect()

    # ─────────────────────────────────────────────────────────────────────────

    def request_reconnect(self) -> bool:
        """Thử kết nối lại với cấu hình hiện tại."""
        self.connected = False
        return self.connect()

    # ─────────────────────────────────────────────────────────────────────────

    def disconnect(self) -> None:
        """Đánh dấu cổng và listener đã đóng."""
        self.connected = False
        self.is_listening = False

    # ─────────────────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Đóng manager giả khi lifespan kết thúc."""
        self.disconnect()

    # ─────────────────────────────────────────────────────────────────────────

    def status(self) -> dict[str, object]:
        """Trả payload runtime tương thích UartManagerV2."""
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "timeout": self.timeout,
            "connected": self.connected,
            "is_listening": self.is_listening,
            "last_error": self.last_error,
            "last_connected_at": None,
            "last_disconnected_at": None,
            "last_received_at": None,
        }

    # ─────────────────────────────────────────────────────────────────────────

    def send_message(self, message: MessageBase) -> bool:
        """Ghi nhận message khi manager đang kết nối."""
        if not self.connected:
            return False
        self.sent.append(message)
        return True

    # ─────────────────────────────────────────────────────────────────────────

    def emit(self, message: MessageBase) -> None:
        """Phát message vào handler giống listener UART thật."""
        handler = self.handlers.get(int(message.MESSAGE_TYPE))
        if callable(handler):
            handler(message)
        if callable(self.generic_handler):
            self.generic_handler(message)


class UartApiTestCase(unittest.TestCase):
    """Xác nhận UART lỗi, phục hồi và lỗi lại không ảnh hưởng FastAPI."""

    def setUp(self) -> None:
        """Tạo app với config và UART manager riêng cho từng test."""
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.config_path = Path(temporary_directory.name) / "config.json"
        self.store = ConfigStore(self.config_path)
        self.store.update_uart(
            UartConfig(port="/dev/missing", auto_connect=True)
        )
        self.manager = FakeUartManager()
        self.monitor = FakeMonitorService(
            ServerSettings(camera_config_path=str(self.config_path))
        )
        self.service = UartService(
            self.store,
            self.monitor.read_snapshot,
            manager=self.manager,
        )
        self.application = create_app(
            self.monitor.settings,
            monitor_factory=lambda _settings: self.monitor,
            config_store=self.store,
            uart_service=self.service,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_server_stays_available_while_uart_changes_between_error_and_ok(self) -> None:
        """Port lỗi và reconnect nhiều lần không được làm health-check thất bại."""
        with TestClient(self.application) as client:
            # Bước 1: auto-connect lỗi nhưng FastAPI vẫn nhận request.
            failed = client.get("/api/uart/status").json()
            self.assertFalse(failed["connected"])
            self.assertIn("/dev/missing", failed["last_error"])
            self.assertEqual(client.get("/health").status_code, 200)

            # Bước 2: đổi port hợp lệ ngay trong runtime phải kết nối được.
            connected = client.put(
                "/api/uart/config",
                json={
                    "port": "/dev/ttyOK",
                    "baudrate": 115200,
                    "timeout": 0.5,
                    "auto_connect": True,
                },
            ).json()
            self.assertTrue(connected["connected"])

            # Bước 3: đổi ngược về port lỗi chỉ làm UART disconnected.
            failed_again = client.put(
                "/api/uart/config",
                json={
                    "port": "/dev/broken",
                    "baudrate": 9600,
                    "timeout": 0.2,
                    "auto_connect": False,
                },
            ).json()
            self.assertFalse(failed_again["connected"])
            self.assertEqual(client.get("/health").status_code, 200)

        self.assertEqual(self.store.get_uart().port, "/dev/broken")

    # ─────────────────────────────────────────────────────────────────────────

    def test_corridor_request_is_answered_and_exposed_in_message_log(self) -> None:
        """GET_CORRIDOR_INFO phải sinh response và hai event RX/TX."""
        with TestClient(self.application) as client:
            client.put(
                "/api/uart/config",
                json={
                    "port": "/dev/ttyOK",
                    "baudrate": 115200,
                    "timeout": 1.0,
                    "auto_connect": True,
                },
            )
            self.manager.emit(GetCorridorInfo(robot_id=7, request_id=42))
            events = client.get("/api/uart/messages").json()

        self.assertEqual(len(self.manager.sent), 1)
        self.assertIsInstance(self.manager.sent[0], CorridorInfo)
        self.assertEqual([event["direction"] for event in events], ["tx", "rx"])
        self.assertEqual(events[0]["request_id"], 42)

    # ─────────────────────────────────────────────────────────────────────────

    def test_websocket_exposes_uart_status_without_requiring_a_device(self) -> None:
        """Dashboard phải nhận heartbeat cả khi chưa kết nối cổng serial."""
        with TestClient(self.application) as client:
            with client.websocket_connect("/ws/uart") as websocket:
                payload = websocket.receive_json()

        self.assertEqual(payload["type"], "uart_update")
        self.assertFalse(payload["status"]["connected"])
        self.assertEqual(payload["messages"], [])


if __name__ == "__main__":
    unittest.main()
