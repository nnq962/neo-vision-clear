"""Kiểm thử UART manager với kết nối serial giả lập trong bộ nhớ."""

from __future__ import annotations

import time
import unittest

import serial

from uart.messages import GetCorridorInfo, MessageType
from uart.uart_manager import BINARY_START_BYTE, UartManagerV2


class _FakeSerial:
    """Mô phỏng phần nhỏ giao diện pyserial mà manager đang sử dụng."""

    def __init__(self, incoming: bytes = b"") -> None:
        """Khởi tạo buffer đọc và đánh dấu kết nối đang mở."""
        self.is_open = True
        self._incoming = bytearray(incoming)
        self.written = bytearray()

    @property
    def in_waiting(self) -> int:
        """Trả số byte đang chờ được đọc trong buffer."""
        return len(self._incoming)

    def read(self, size: int) -> bytes:
        """Đọc tối đa size byte từ buffer giống serial có timeout."""
        data = bytes(self._incoming[:size])
        del self._incoming[:size]
        return data

    def write(self, data: bytes) -> int:
        """Ghi byte vào buffer output và trả số byte đã ghi."""
        self.written.extend(data)
        return len(data)

    def close(self) -> None:
        """Đánh dấu kết nối giả lập đã đóng."""
        self.is_open = False


class UartManagerTests(unittest.TestCase):
    """Kiểm tra framing, decoding và dispatch handler của UART manager."""

    # ─────────────────────────────────────────────────────────────────────────

    def test_sends_complete_wire_frame(self) -> None:
        """Manager phải thêm start byte và length bên ngoài message packet."""
        manager = UartManagerV2()
        connection = _FakeSerial()
        manager.serial_conn = connection
        message = GetCorridorInfo(robot_id=3, request_id=120)

        sent = manager.send_message(message)

        self.assertTrue(sent)
        self.assertEqual(
            bytes(connection.written).hex(" "),
            "aa 06 10 03 78 00 24 c5",
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_receives_frame_and_calls_registered_handler(self) -> None:
        """Manager phải decode frame rồi dispatch đúng message type."""
        message = GetCorridorInfo(robot_id=4, request_id=321)
        body = message.encode()
        frame = bytes([BINARY_START_BYTE, len(body)]) + body
        manager = UartManagerV2()
        manager.serial_conn = _FakeSerial(frame)
        received = []
        manager.set_handler(MessageType.GET_CORRIDOR_INFO, received.append)

        result = manager.receive_message()

        self.assertEqual(result, message)
        self.assertEqual(received, [message])

    # ─────────────────────────────────────────────────────────────────────────

    def test_sends_and_receives_through_pyserial_loopback(self) -> None:
        """Message gửi qua pyserial loopback phải được nhận lại nguyên vẹn."""
        manager = UartManagerV2(timeout=0.2)
        manager.serial_conn = serial.serial_for_url("loop://", timeout=0.2)
        message = GetCorridorInfo(robot_id=9, request_id=1234)
        received = []
        manager.set_handler(MessageType.GET_CORRIDOR_INFO, received.append)

        try:
            self.assertTrue(manager.send_message(message))

            # Bước 1: chờ có giới hạn để test ổn định trên máy chạy chậm.
            deadline = time.monotonic() + 1.0
            result = None
            while result is None and time.monotonic() < deadline:
                result = manager.receive_message()
                if result is None:
                    time.sleep(0.01)

            self.assertEqual(result, message)
            self.assertEqual(received, [message])
            self.assertEqual(manager.latest_received_message, message)
        finally:
            manager.close()


if __name__ == "__main__":
    unittest.main()
