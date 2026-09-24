from __future__ import annotations

import struct
import threading
import time
from typing import Callable, Optional

import serial

from uart.messages import MessageBase
from utils import LOGGER


DEFAULT_PORT = "/dev/ttyS4"
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1
BINARY_START_BYTE = 0xAA  # byte đánh dấu đầu mỗi gói nhị phân
MAX_BODY_SIZE = 0xFF  # LENGTH là uint8, nên phần thân (message_type+payload+checksum) tối đa 255 byte


# ─────────────────────────────────────────────────────────────────────────────
class UartManagerV2:
    """
    Phiên bản UART manager chỉ xử lý giao thức nhị phân (không còn JSON/string).

    Khung mỗi gói tin trên dây (wire format):
        [BINARY_START_BYTE][LENGTH][message_type + payload + checksum]
                1 byte      1 byte      N byte (= giá trị của LENGTH)

    LENGTH là tổng số byte còn lại NGAY SAU chính nó (message_type + payload +
    checksum gộp lại), không phụ thuộc vào MessageBase._registry hay FORMAT của
    từng loại message. Nhờ vậy bên đọc (kể cả một bên trung gian chỉ forward dữ
    liệu, không biết ý nghĩa từng loại message) vẫn xác định được chính xác
    điểm kết thúc gói: đọc 1 byte LENGTH rồi đọc đúng bấy nhiêu byte tiếp theo.
    """

    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Khởi tạo manager UART nhưng chưa mở cổng serial."""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: Optional[serial.Serial] = None

        self.latest_received_message: Optional[MessageBase] = None
        self.is_listening = False
        self.listen_thread: Optional[threading.Thread] = None
        self.last_error: Optional[str] = None
        self.last_connected_at: Optional[float] = None
        self.last_disconnected_at: Optional[float] = None
        self.last_received_at: Optional[float] = None

        # Handler riêng cho từng loại message, đăng ký qua set_handler(MessageType.X, callback)
        self._handlers: dict[int, Callable[[MessageBase], None]] = {}
        # Subscriber bổ sung cho từng loại message. Khác set_handler(), add_handler()
        # không ghi đè handler chính đã được module khác đăng ký.
        self._additional_handlers: dict[int, list[Callable[[MessageBase], None]]] = {}
        # Handler chung, được gọi cho MỌI message nhận được (nếu có đăng ký)
        self._generic_handler: Optional[Callable[[MessageBase], None]] = None

        self._lock = threading.RLock()

    # ─────────────────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        """Mở cổng Serial và khởi động thread lắng nghe nếu thành công."""
        with self._lock:
            if self._is_connected_unlocked():
                return True

            if not self._open_serial_unlocked():
                return False

        self.start_listening()
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def start_listening(self) -> None:
        """Khởi động luồng nền đọc dữ liệu UART."""
        with self._lock:
            if self.is_listening:
                return

            self.is_listening = True
            self.listen_thread = threading.Thread(
                target=self._listen_loop,
                daemon=True,
                name="uart-listener-v2",
            )
            self.listen_thread.start()
            LOGGER.info("Đã khởi động luồng lắng nghe UART (binary v2).")

    # ─────────────────────────────────────────────────────────────────────────
    def stop_listening(self) -> None:
        """Dừng luồng lắng nghe UART."""
        with self._lock:
            self.is_listening = False
            thread = self.listen_thread

        if (
            thread
            and thread.is_alive()
            and threading.current_thread() is not thread
        ):
            thread.join(timeout=2)

        with self._lock:
            if self.listen_thread is thread:
                self.listen_thread = None

    # ─────────────────────────────────────────────────────────────────────────
    def disconnect(self) -> None:
        """Dừng lắng nghe và đóng cổng Serial hiện tại."""
        self.stop_listening()
        self._close_serial()

    # ─────────────────────────────────────────────────────────────────────────
    def request_reconnect(self) -> bool:
        """Đóng cổng hiện tại nếu cần rồi thử kết nối lại."""
        self._close_serial()
        return self.connect()

    # ─────────────────────────────────────────────────────────────────────────
    def reconfigure(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """Cập nhật cấu hình UART và khởi động lại kết nối nếu cần."""
        changed = self.configure(port, baudrate, timeout)
        if not changed and self.is_connected():
            LOGGER.info("UART config unchanged, skip reconnect.")
            return True

        if not changed:
            LOGGER.info("UART config unchanged but disconnected, retry connect.")
        else:
            LOGGER.info(
                f"Đang khởi động lại UART với port={self.port}, "
                f"baudrate={self.baudrate}"
            )
        return self.connect()

    # ─────────────────────────────────────────────────────────────────────────
    def configure(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """Áp dụng tham số mới mà chưa tự mở lại cổng serial."""
        with self._lock:
            next_port = port if port is not None else self.port
            next_baudrate = baudrate if baudrate is not None else self.baudrate
            next_timeout = timeout if timeout is not None else self.timeout
            unchanged = (
                next_port == self.port
                and next_baudrate == self.baudrate
                and next_timeout == self.timeout
            )

        if unchanged:
            return False

        self.disconnect()
        with self._lock:
            self.port = next_port
            self.baudrate = next_baudrate
            self.timeout = next_timeout
        return True

    # ─────────────────────────────────────────────────────────────────────────
    def send_message(self, message: MessageBase) -> bool:
        """Đóng khung và gửi một message hành lang xuống cổng UART."""
        try:
            body = message.encode()  # message_type + payload + checksum
        except (TypeError, ValueError, struct.error) as e:
            self.last_error = str(e)
            LOGGER.error(f"Dữ liệu vượt phạm vi kiểu khi encode {type(message).__name__}: {e}")
            return False

        if len(body) > MAX_BODY_SIZE:
            self.last_error = (
                f"{type(message).__name__} dài {len(body)} byte, vượt giới hạn LENGTH 1 byte ({MAX_BODY_SIZE})."
            )
            LOGGER.error(self.last_error)
            return False

        packet = bytes([BINARY_START_BYTE, len(body)]) + body

        with self._lock:
            conn = self.serial_conn
            if conn is None or not conn.is_open:
                LOGGER.error("Cổng UART chưa mở.")
                return False

            try:
                conn.write(packet)
                return True
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi gửi message nhị phân: {e}")
                self._close_serial_unlocked()
                return False

    # ─────────────────────────────────────────────────────────────────────────
    def receive_message(self) -> Optional[MessageBase]:
        """Đọc và tự động phân tích 1 gói nhị phân từ UART, đồng thời cập nhật state
        + gọi handler tương ứng (giống receive_data() ở bản v1)."""
        message = self._read_one_message()
        if message is None:
            return None

        self._handle_received_message(message)
        return message

    # ─────────────────────────────────────────────────────────────────────────
    def status(self) -> dict:
        """Trả trạng thái runtime của UART manager."""
        with self._lock:
            return {
                "port": self.port,
                "baudrate": self.baudrate,
                "timeout": self.timeout,
                "connected": self._is_connected_unlocked(),
                "is_listening": self.is_listening,
                "last_error": self.last_error,
                "last_connected_at": self.last_connected_at,
                "last_disconnected_at": self.last_disconnected_at,
                "last_received_at": self.last_received_at,
            }

    # ─────────────────────────────────────────────────────────────────────────
    def set_handler(self, message_type: int, handler: Optional[Callable[[MessageBase], None]]) -> None:
        """Đăng ký callback riêng cho 1 loại message cụ thể.
        Ví dụ: uart.set_handler(MessageType.GET_CORRIDOR_INFO, on_request)."""
        with self._lock:
            if handler is None:
                self._handlers.pop(message_type, None)
            else:
                self._handlers[message_type] = handler

    # ─────────────────────────────────────────────────────────────────────────
    def add_handler(self, message_type: int, handler: Callable[[MessageBase], None]) -> None:
        """Thêm subscriber mà không ghi đè handler chính của message type."""
        with self._lock:
            handlers = self._additional_handlers.setdefault(int(message_type), [])
            if handler not in handlers:
                handlers.append(handler)

    # ─────────────────────────────────────────────────────────────────────────
    def remove_handler(self, message_type: int, handler: Callable[[MessageBase], None]) -> None:
        """Gỡ một subscriber đã thêm bằng add_handler()."""
        with self._lock:
            handlers = self._additional_handlers.get(int(message_type))
            if handlers is None:
                return
            try:
                handlers.remove(handler)
            except ValueError:
                return
            if not handlers:
                self._additional_handlers.pop(int(message_type), None)

    # ─────────────────────────────────────────────────────────────────────────
    def set_generic_handler(self, handler: Optional[Callable[[MessageBase], None]]) -> None:
        """Đăng ký callback được gọi cho MỌI message nhận được, bất kể loại gì
        (hữu ích cho việc log/monitor chung)."""
        with self._lock:
            self._generic_handler = handler

    # ─────────────────────────────────────────────────────────────────────────
    def is_connected(self) -> bool:
        """Trả True khi đối tượng serial hiện tại vẫn đang mở."""
        with self._lock:
            return self._is_connected_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def close(self) -> None:
        """Đóng kết nối an toàn."""
        self.disconnect()

    # ─────────────────────────────────────────────────────────────────────────
    def _listen_loop(self) -> None:
        """Vòng lặp nền liên tục đọc UART."""
        while True:
            with self._lock:
                if not self.is_listening:
                    return
                connected = self._is_connected_unlocked()

            if not connected:
                LOGGER.warning("Mất kết nối UART, đang thử kết nối lại...")
                time.sleep(2)
                with self._lock:
                    if not self.is_listening:
                        return

                    self._close_serial_unlocked()
                    self._open_serial_unlocked()
                continue

            self.receive_message()

            time.sleep(0.01)

    # ─────────────────────────────────────────────────────────────────────────
    def _read_one_message(self) -> Optional[MessageBase]:
        """Đọc đúng 1 gói nhị phân hoàn chỉnh từ UART (blocking theo số byte cần thiết,
        không dùng readline). Trả None nếu chưa có gói, sai start byte, đọc thiếu byte,
        message_type không rõ, hoặc CRC sai."""
        with self._lock:
            conn = self.serial_conn
            if conn is None or not conn.is_open:
                return None

            try:
                if conn.in_waiting <= 0:
                    return None

                start = conn.read(1)
                if not start or start[0] != BINARY_START_BYTE:
                    LOGGER.warning(f"Byte đầu không khớp start byte nhị phân: {start!r}")
                    return None

                length_byte = conn.read(1)
                if not length_byte:
                    return None
                length = length_byte[0]

                packet = conn.read(length)
                if len(packet) != length:
                    LOGGER.warning("Đọc thiếu byte, gói nhị phân không đầy đủ.")
                    return None
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi đọc message nhị phân: {e}")
                self._close_serial_unlocked()
                return None

        message = MessageBase.decode_any(packet)
        if message is None:
            LOGGER.warning("Không giải mã được gói nhị phân (CRC sai hoặc message_type không rõ).")
        return message

    # ─────────────────────────────────────────────────────────────────────────
    def _handle_received_message(self, message: MessageBase) -> None:
        """Cập nhật state rồi gọi các handler phù hợp ở ngoài critical section."""
        with self._lock:
            now = time.time()
            self.last_received_at = now
            self.latest_received_message = message

            specific_handler = self._handlers.get(int(message.MESSAGE_TYPE))
            additional_handlers = tuple(
                self._additional_handlers.get(int(message.MESSAGE_TYPE), ())
            )
            generic_handler = self._generic_handler

        if specific_handler is not None:
            try:
                specific_handler(message)
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi xử lý handler cho {type(message).__name__}: {e}")

        for handler in additional_handlers:
            try:
                handler(message)
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(
                    f"Lỗi khi xử lý subscriber cho {type(message).__name__}: {e}"
                )

        if generic_handler is not None:
            try:
                generic_handler(message)
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi xử lý generic handler: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    def _close_serial(self) -> None:
        """Đóng kết nối serial hiện tại dưới lock của manager."""
        with self._lock:
            self._close_serial_unlocked()

    # ─────────────────────────────────────────────────────────────────────────
    def _open_serial_unlocked(self) -> bool:
        """Mở cổng serial khi caller đang giữ lock và trả kết quả thành công."""
        try:
            self.serial_conn = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
            )
            self.last_error = None
            self.last_connected_at = time.time()
            LOGGER.info(f"Đã kết nối UART tại {self.port}")
            return True
        except (serial.SerialException, ValueError, OSError) as e:
            self.serial_conn = None
            self.last_error = str(e)
            LOGGER.error(f"Lỗi mở cổng {self.port}: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    def _close_serial_unlocked(self) -> None:
        """Đóng cổng serial khi caller đang giữ lock và cập nhật timestamp."""
        conn = self.serial_conn
        self.serial_conn = None

        if conn is not None and conn.is_open:
            try:
                conn.close()
                LOGGER.info("Đã ngắt kết nối UART.")
            except Exception as e:
                self.last_error = str(e)
                LOGGER.error(f"Lỗi khi đóng UART: {e}")

        self.last_disconnected_at = time.time()

    # ─────────────────────────────────────────────────────────────────────────
    def _is_connected_unlocked(self) -> bool:
        """Kiểm tra kết nối mà không tự lấy lock của manager."""
        return self.serial_conn is not None and self.serial_conn.is_open
