"""Điều phối UART độc lập để lỗi serial không ảnh hưởng FastAPI."""

from __future__ import annotations

from collections import deque
import threading
import time
from typing import Callable

from serial.tools import list_ports

from server.models.uart import UartConfig, UartMessageEvent, UartStatus
from server.services.config_store import ConfigStore
from server.services.snapshot_store import SnapshotRead
from uart.messages import (
    DATA_AVAILABLE_FLAG,
    CorridorInfo,
    CorridorStatus,
    GetCorridorInfo,
    MessageBase,
    MessageType,
)
from uart.uart_manager import BINARY_START_BYTE, UartManagerV2


SnapshotReader = Callable[[], SnapshotRead]


class UartService:
    """Quản lý cấu hình, kết nối, phản hồi và nhật ký message UART."""

    def __init__(
        self,
        store: ConfigStore,
        snapshot_reader: SnapshotReader,
        manager: UartManagerV2 | None = None,
        history_size: int = 200,
    ) -> None:
        """Khởi tạo service nhưng chưa mở cổng serial."""
        self._store = store
        self._snapshot_reader = snapshot_reader
        self._manager = manager or UartManagerV2()
        self._config = store.get_uart()
        self._events: deque[UartMessageEvent] = deque(maxlen=history_size)
        self._sequence = 0
        self._lock = threading.RLock()

        # Bước 1: handler nghiệp vụ phản hồi request; generic ghi nhận loại khác.
        self._manager.set_handler(
            MessageType.GET_CORRIDOR_INFO,
            self._handle_corridor_request,
        )
        self._manager.set_generic_handler(self._handle_generic_message)

    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> UartStatus:
        """Áp dụng cấu hình đã lưu và tùy chọn kết nối khi server khởi động."""
        with self._lock:
            self._config = self._store.get_uart()
            config = self._config.model_copy(deep=True)

        # Bước 1: luôn nạp đúng tham số nhưng chỉ mở serial khi auto_connect bật.
        self._manager.configure(config.port, config.baudrate, config.timeout)
        if config.auto_connect:
            self._manager.connect()
        return self.status()

    # ─────────────────────────────────────────────────────────────────────────

    def configure(self, config: UartConfig) -> UartStatus:
        """Lưu cấu hình mới rồi reconnect mà không phát sinh lỗi lên FastAPI."""
        # Bước 1: lưu trước để cổng lỗi vẫn có thể được sửa ở request kế tiếp.
        saved = self._store.update_uart(config)
        with self._lock:
            self._config = saved

        # Bước 2: reconfigure trả False khi mở lỗi thay vì làm hỏng request/server.
        self._manager.reconfigure(saved.port, saved.baudrate, saved.timeout)
        return self.status()

    # ─────────────────────────────────────────────────────────────────────────

    def connect(self) -> UartStatus:
        """Thử mở lại cổng theo cấu hình hiện tại và trả trạng thái kết quả."""
        self._manager.request_reconnect()
        return self.status()

    # ─────────────────────────────────────────────────────────────────────────

    def disconnect(self) -> UartStatus:
        """Đóng UART chủ động mà không thay đổi cấu hình đã lưu."""
        self._manager.disconnect()
        return self.status()

    # ─────────────────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Giải phóng thread và cổng serial khi FastAPI shutdown."""
        self._manager.close()

    # ─────────────────────────────────────────────────────────────────────────

    def status(self) -> UartStatus:
        """Trả snapshot thread-safe của cấu hình và trạng thái manager."""
        runtime = self._manager.status()
        with self._lock:
            config = self._config.model_copy(deep=True)
        payload = config.model_dump()
        payload.update(runtime)
        return UartStatus.model_validate(payload)

    # ─────────────────────────────────────────────────────────────────────────

    def list_ports(self) -> list[str]:
        """Liệt kê và sắp xếp các thiết bị serial hệ điều hành phát hiện."""
        # Bước 1: chỉ trả device path, không đưa object pyserial qua API.
        return sorted({item.device for item in list_ports.comports()})

    # ─────────────────────────────────────────────────────────────────────────

    def events_after(self, sequence: int) -> list[UartMessageEvent]:
        """Trả các sự kiện có sequence lớn hơn cursor của client."""
        with self._lock:
            return [
                event.model_copy(deep=True)
                for event in self._events
                if event.sequence > sequence
            ]

    # ─────────────────────────────────────────────────────────────────────────

    def recent_events(self) -> list[UartMessageEvent]:
        """Trả lịch sử message mới nhất trước để khởi tạo dashboard."""
        with self._lock:
            return [event.model_copy(deep=True) for event in reversed(self._events)]

    # ─────────────────────────────────────────────────────────────────────────

    def clear_events(self) -> None:
        """Xóa lịch sử dashboard nhưng giữ nguyên kết nối và sequence."""
        with self._lock:
            self._events.clear()

    # ─────────────────────────────────────────────────────────────────────────

    def _handle_corridor_request(self, message: MessageBase) -> None:
        """Ghi nhận request và gửi snapshot hành lang tương ứng cho robot."""
        if not isinstance(message, GetCorridorInfo):
            return
        self._record_event("rx", message, "Robot yêu cầu snapshot lối đi mới nhất")

        # Bước 1: đọc snapshot đúng một lần để status, age và phép đo đồng bộ.
        response = self._build_corridor_response(message, self._snapshot_reader())
        if self._manager.send_message(response):
            self._record_event("tx", response, self._response_summary(response))

    # ─────────────────────────────────────────────────────────────────────────

    def _handle_generic_message(self, message: MessageBase) -> None:
        """Ghi nhận các message không được handler nghiệp vụ xử lý riêng."""
        if isinstance(message, GetCorridorInfo):
            return
        self._record_event("rx", message, "Đã nhận message UART")

    # ─────────────────────────────────────────────────────────────────────────

    def _build_corridor_response(
        self,
        request: GetCorridorInfo,
        reading: SnapshotRead,
    ) -> CorridorInfo:
        """Chuyển snapshot nội bộ thành response nhị phân có miền an toàn."""
        status_map = {
            "ok": CorridorStatus.OK,
            "warming_up": CorridorStatus.WARMING_UP,
            "stale": CorridorStatus.STALE,
            "error": CorridorStatus.ERROR,
        }
        status = status_map[reading.status]
        if reading.snapshot is None or status in {
            CorridorStatus.WARMING_UP,
            CorridorStatus.ERROR,
        }:
            return CorridorInfo.without_data(
                request.robot_id,
                request.request_id,
                status,
            )

        # Bước 1: đổi mét sang millimet và chặn theo miền biểu diễn protocol.
        snapshot = reading.snapshot
        return CorridorInfo(
            robot_id=request.robot_id,
            request_id=request.request_id,
            status=status,
            flags=DATA_AVAILABLE_FLAG,
            age_ms=min(max(reading.age_ms or 0, 0), 0xFFFFFFFE),
            maximum_passable_width_mm=self._unsigned_mm(
                snapshot.maximum_passable_width_meters
            ),
            walkway_width_mm=self._unsigned_mm(snapshot.walkway_width_meters),
            bottleneck_y_mm=self._signed_mm(snapshot.bottleneck_y_meters),
            frame_index=min(max(snapshot.frame_index, 0), 0xFFFFFFFF),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _record_event(
        self,
        direction: str,
        message: MessageBase,
        summary: str,
    ) -> None:
        """Thêm một event đã encode vào ring buffer theo thứ tự tăng dần."""
        robot_id = int(getattr(message, "robot_id", 0))
        request_id = int(getattr(message, "request_id", 0))
        with self._lock:
            self._sequence += 1
            self._events.append(
                UartMessageEvent(
                    sequence=self._sequence,
                    timestamp=time.time(),
                    direction=direction,
                    message_type=message.MESSAGE_TYPE.name,
                    robot_id=robot_id,
                    request_id=request_id,
                    summary=summary,
                    frame=self._wire_frame(message),
                )
            )

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _wire_frame(message: MessageBase) -> str:
        """Mã hóa message thành chuỗi hex đầy đủ cả start byte và length."""
        body = message.encode()
        frame = bytes([BINARY_START_BYTE, len(body)]) + body
        return frame.hex(" ").upper()

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _response_summary(message: CorridorInfo) -> str:
        """Tạo mô tả ngắn của response để dashboard dễ đọc."""
        if not message.data_available:
            return message.status.name
        return (
            f"{message.status.name} · rộng tối đa "
            f"{message.maximum_passable_width_mm} mm · snapshot {message.age_ms} ms"
        )

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _unsigned_mm(value_meters: float) -> int:
        """Đổi mét thành uint16 millimet có chặn biên."""
        return min(max(int(round(value_meters * 1000)), 0), 0xFFFF)

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _signed_mm(value_meters: float) -> int:
        """Đổi mét thành int32 millimet có chặn biên."""
        value = int(round(value_meters * 1000))
        return min(max(value, -(2**31)), 2**31 - 1)
