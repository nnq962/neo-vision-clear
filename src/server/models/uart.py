"""Schema cấu hình, trạng thái và sự kiện UART của FastAPI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UartConfig(BaseModel):
    """Cấu hình UART bền vững có thể thay đổi khi server đang chạy."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    port: str = Field(default="/dev/ttyS4", min_length=1, max_length=255)
    baudrate: int = Field(default=115200, ge=300, le=4_000_000)
    timeout: float = Field(default=1.0, ge=0.05, le=30.0)
    auto_connect: bool = False


class UartStatus(UartConfig):
    """Trạng thái thực tế của UART kèm cấu hình đang được áp dụng."""

    connected: bool
    is_listening: bool
    last_error: str | None = None
    last_connected_at: float | None = None
    last_disconnected_at: float | None = None
    last_received_at: float | None = None


class UartPortsResponse(BaseModel):
    """Danh sách cổng serial đang được hệ điều hành phát hiện."""

    ports: list[str]


class UartMessageEvent(BaseModel):
    """Một message UART đã nhận hoặc gửi để hiển thị trên dashboard."""

    sequence: int
    timestamp: float
    direction: Literal["rx", "tx"]
    message_type: str
    robot_id: int
    request_id: int
    summary: str
    frame: str
    checksum_valid: bool = True


class UartStreamPayload(BaseModel):
    """Payload WebSocket gồm trạng thái mới nhất và các message mới."""

    type: Literal["uart_update"] = "uart_update"
    status: UartStatus
    messages: list[UartMessageEvent]

