"""REST API và WebSocket quản lý UART khi FastAPI đang chạy."""

from __future__ import annotations

import asyncio
from typing import List

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from server.dependencies import get_uart_service
from server.models.uart import (
    UartConfig,
    UartMessageEvent,
    UartPortsResponse,
    UartStatus,
    UartStreamPayload,
)
from server.services.uart import UartService


router = APIRouter(tags=["uart"])


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/api/uart/status", response_model=UartStatus)
def get_uart_status(
    service: Annotated[UartService, Depends(get_uart_service)],
) -> UartStatus:
    """Trả trạng thái UART mà không thay đổi kết nối."""
    return service.status()


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/api/uart/ports", response_model=UartPortsResponse)
def get_uart_ports(
    service: Annotated[UartService, Depends(get_uart_service)],
) -> UartPortsResponse:
    """Quét các cổng serial hiện có trên máy chạy FastAPI."""
    return UartPortsResponse(ports=service.list_ports())


# ─────────────────────────────────────────────────────────────────────────────


@router.put("/api/uart/config", response_model=UartStatus)
def update_uart_config(
    payload: UartConfig,
    service: Annotated[UartService, Depends(get_uart_service)],
) -> UartStatus:
    """Lưu cấu hình mới và thử reconnect mà không làm lỗi server."""
    return service.configure(payload)


# ─────────────────────────────────────────────────────────────────────────────


@router.post("/api/uart/connect", response_model=UartStatus)
def connect_uart(
    service: Annotated[UartService, Depends(get_uart_service)],
) -> UartStatus:
    """Thử kết nối lại UART theo cấu hình đang lưu."""
    return service.connect()


# ─────────────────────────────────────────────────────────────────────────────


@router.post("/api/uart/disconnect", response_model=UartStatus)
def disconnect_uart(
    service: Annotated[UartService, Depends(get_uart_service)],
) -> UartStatus:
    """Ngắt UART chủ động nhưng vẫn giữ FastAPI và cấu hình hiện tại."""
    return service.disconnect()


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/api/uart/messages", response_model=List[UartMessageEvent])
def get_uart_messages(
    service: Annotated[UartService, Depends(get_uart_service)],
) -> list[UartMessageEvent]:
    """Trả lịch sử message trong bộ nhớ theo thứ tự mới nhất trước."""
    return service.recent_events()


# ─────────────────────────────────────────────────────────────────────────────


@router.delete("/api/uart/messages", status_code=204)
def clear_uart_messages(
    service: Annotated[UartService, Depends(get_uart_service)],
) -> None:
    """Xóa log message trên dashboard mà không ngắt kết nối UART."""
    service.clear_events()


# ─────────────────────────────────────────────────────────────────────────────


@router.websocket("/ws/uart")
async def uart_websocket(
    websocket: WebSocket,
    service: Annotated[UartService, Depends(get_uart_service)],
) -> None:
    """Phát trạng thái cùng message RX/TX mới cho dashboard UART."""
    await websocket.accept()
    cursor = 0
    try:
        while True:
            # Bước 1: cursor tránh gửi lặp message nhưng vẫn heartbeat trạng thái.
            messages = service.events_after(cursor)
            if messages:
                cursor = messages[-1].sequence
            payload = UartStreamPayload(
                status=service.status(),
                messages=messages,
            )
            await websocket.send_json(payload.model_dump(mode="json"))

            # Bước 2: chờ disconnect có timeout để không giữ session đã đóng.
            try:
                event = await asyncio.wait_for(websocket.receive(), timeout=0.5)
                if event["type"] == "websocket.disconnect":
                    return
            except asyncio.TimeoutError:
                continue
    except (WebSocketDisconnect, RuntimeError):
        # Client đóng trang là kết thúc bình thường, không ảnh hưởng UART thread.
        return
