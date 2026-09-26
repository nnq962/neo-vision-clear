"""Publisher WebSocket một chiều từ Jetson tới Aggregator."""

from __future__ import annotations

from collections import OrderedDict
import json
import threading
from typing import Optional
from urllib.parse import quote

from websockets.sync.client import connect

from server.models.aggregator import CameraMeasurementMessage
from server.settings import ServerSettings
from utils.logger import LOGGER


class AggregatorPublisher:
    """Giữ kết nối WS, tự reconnect và chỉ giữ message mới nhất mỗi camera."""

    def __init__(self, settings: ServerSettings) -> None:
        """Khởi tạo publisher nhưng chưa tạo thread hoặc kết nối mạng."""
        self._base_url = settings.aggregator_ws_base_url
        self._jetson_id = settings.jetson_id
        self._reconnect_seconds = settings.aggregator_reconnect_seconds
        self._condition = threading.Condition()
        self._pending: "OrderedDict[str, CameraMeasurementMessage]" = OrderedDict()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ─────────────────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        """Cho biết publisher đã được cấu hình URL Aggregator hay chưa."""
        return self._base_url is not None

    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Khởi động thread reconnect khi publisher đã được cấu hình."""
        if not self.enabled:
            LOGGER.info("Chưa cấu hình Aggregator WS; publisher đang tắt.")
            return
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="aggregator-publisher",
            )
            self._thread.start()

    # ─────────────────────────────────────────────────────────────────────────

    def publish(self, message: CameraMeasurementMessage) -> None:
        """Đưa message mới nhất của camera vào hàng đợi không chặn inference."""
        if not self.enabled:
            return
        with self._condition:
            # Bước 1: thay payload cũ cùng camera để mạng chậm không tích backlog.
            self._pending.pop(message.camera_id, None)
            self._pending[message.camera_id] = message.model_copy(deep=True)
            self._condition.notify()

    # ─────────────────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Dừng publisher và chờ ngắn để thread giải phóng socket."""
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    # ─────────────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        """Kết nối lại vô hạn và gửi tuần tự các payload đang chờ."""
        assert self._base_url is not None
        target_url = (
            f"{self._base_url.rstrip('/')}/{quote(self._jetson_id, safe='')}"
        )
        while not self._stop_event.is_set():
            try:
                # Bước 1: timeout ngắn giúp shutdown không phải chờ mạng quá lâu.
                with connect(
                    target_url,
                    open_timeout=3,
                    close_timeout=1,
                ) as websocket:
                    LOGGER.info("Đã kết nối Aggregator tại %s.", target_url)
                    self._send_pending(websocket)
            except Exception as exc:
                if not self._stop_event.is_set():
                    LOGGER.warning(
                        "Chưa gửi được dữ liệu tới Aggregator: %s",
                        exc,
                    )
                    self._stop_event.wait(self._reconnect_seconds)

    # ─────────────────────────────────────────────────────────────────────────

    def _send_pending(self, websocket) -> None:
        """Gửi message cho tới khi socket lỗi hoặc publisher được dừng."""
        while not self._stop_event.is_set():
            message = self._next_message()
            if message is None:
                continue
            try:
                websocket.send(
                    json.dumps(
                        message.model_dump(mode="json", exclude_none=True),
                        separators=(",", ":"),
                    )
                )
            except Exception:
                # Bước 1: giữ lại payload chưa gửi để retry trên kết nối tiếp theo.
                with self._condition:
                    if message.camera_id not in self._pending:
                        self._pending[message.camera_id] = message
                raise

    # ─────────────────────────────────────────────────────────────────────────

    def _next_message(self) -> Optional[CameraMeasurementMessage]:
        """Chờ có dữ liệu và lấy camera cũ nhất trong hàng đợi latest-wins."""
        with self._condition:
            while not self._pending and not self._stop_event.is_set():
                self._condition.wait(timeout=0.5)
            if not self._pending:
                return None
            _camera_id, message = self._pending.popitem(last=False)
            return message
