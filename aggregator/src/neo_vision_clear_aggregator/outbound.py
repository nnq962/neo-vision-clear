"""Kết nối WebSocket outbound từ Aggregator tới server nhận quyết định."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Optional

from websockets.asyncio.client import connect

from neo_vision_clear_aggregator.config import OutboundConfig
from neo_vision_clear_aggregator.models import CorridorDecision, OutboundStatus


LOGGER = logging.getLogger(__name__)


class OutboundPublisher:
    """Gửi quyết định latest-wins và tự kết nối lại khi WS đích gián đoạn."""

    def __init__(self, config: OutboundConfig) -> None:
        """Khởi tạo queue một phần tử nhưng chưa tạo background task."""
        self._config = config
        self._queue: asyncio.Queue[CorridorDecision] = asyncio.Queue(maxsize=1)
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._sent_messages = 0
        self._last_sent_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[datetime] = None
        self._last_payload: Optional[CorridorDecision] = None

    # ─────────────────────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        """Cho biết kết nối outbound đã được bật trong config hay chưa."""
        return self._config.enabled

    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Khởi động task gửi nền trong event loop hiện tại."""
        if not self.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="aggregator-outbound")

    # ─────────────────────────────────────────────────────────────────────────

    async def publish(self, decision: CorridorDecision) -> None:
        """Thay quyết định đang chờ bằng phiên bản mới nhất mà không block ingest."""
        if not self.enabled:
            return
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(decision.model_copy(deep=True))

    # ─────────────────────────────────────────────────────────────────────────

    async def reconfigure(self, config: OutboundConfig) -> None:
        """Đóng kết nối cũ và áp dụng endpoint outbound mới ngay lập tức."""
        # Bước 1: task cũ phải dừng trước khi đổi config dùng chung.
        await self.close()
        self._config = config
        self._connected = False
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self.start()

    # ─────────────────────────────────────────────────────────────────────────

    def status(self) -> OutboundStatus:
        """Trả snapshot trạng thái gửi hiện tại cho dashboard."""
        return OutboundStatus(
            enabled=self.enabled,
            websocket_url=self._config.websocket_url,
            connected=self._connected,
            queued_messages=self._queue.qsize(),
            sent_messages=self._sent_messages,
            last_sent_at=self._last_sent_at,
            last_error=self._last_error,
            last_error_at=self._last_error_at,
            last_payload=(
                self._last_payload.model_copy(deep=True)
                if self._last_payload is not None
                else None
            ),
        )

    # ─────────────────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Hủy background task khi FastAPI shutdown."""
        if self._task is None:
            self._connected = False
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._connected = False

    # ─────────────────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        """Kết nối lại vô hạn và bảo toàn message bị lỗi gửi để retry."""
        assert self._config.websocket_url is not None
        pending: Optional[CorridorDecision] = None
        while True:
            try:
                async with connect(
                    self._config.websocket_url,
                    open_timeout=3,
                    close_timeout=1,
                ) as websocket:
                    self._connected = True
                    self._last_error = None
                    self._last_error_at = None
                    LOGGER.info(
                        "Đã kết nối WS server đích tại %s.",
                        self._config.websocket_url,
                    )
                    while True:
                        if pending is None:
                            pending = await self._queue.get()
                        await websocket.send(
                            json.dumps(
                                pending.model_dump(mode="json", exclude_none=True),
                                separators=(",", ":"),
                            )
                        )
                        self._sent_messages += 1
                        self._last_sent_at = datetime.now(timezone.utc)
                        self._last_payload = pending.model_copy(deep=True)
                        pending = None
            except asyncio.CancelledError:
                self._connected = False
                raise
            except Exception as exc:
                self._connected = False
                self._last_error = str(exc)
                self._last_error_at = datetime.now(timezone.utc)
                LOGGER.warning("WS server đích chưa sẵn sàng: %s", exc)
                await asyncio.sleep(self._config.reconnect_seconds)
