"""WebSocket request-response cung cấp snapshot hành lang mới nhất."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from server.dependencies import get_monitor_service
from server.models import (
    CorridorInfoData,
    CorridorInfoRequest,
    CorridorInfoResponse,
    ProtocolErrorResponse,
)
from server.services.monitor import MonitorService


router = APIRouter(tags=["websocket"])


# ─────────────────────────────────────────────────────────────────────────────


@router.websocket("/ws/corridor")
async def corridor_websocket(
    websocket: WebSocket,
    service: Annotated[MonitorService, Depends(get_monitor_service)],
) -> None:
    """Nhận yêu cầu và trả snapshot hiện tại trên cùng kết nối WebSocket."""
    await websocket.accept()
    try:
        while True:
            # Bước 1: nhận và kiểm tra message trước khi truy cập snapshot.
            payload = None
            try:
                payload = await websocket.receive_json()
                request = CorridorInfoRequest.model_validate(payload)
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                request_id = (
                    payload.get("request_id")
                    if isinstance(payload, dict)
                    and isinstance(payload.get("request_id"), str)
                    else None
                )
                response = ProtocolErrorResponse(
                    request_id=request_id,
                    error=str(exc),
                )
                await websocket.send_json(response.model_dump(mode="json"))
                continue

            # Bước 2: đọc atomically snapshot và giữ nguyên request_id để robot
            # ghép response với request khi có nhiều yêu cầu nối tiếp.
            reading = service.snapshot_store.read(
                service.settings.snapshot_max_age_seconds
            )
            data = (
                CorridorInfoData.from_snapshot(reading.snapshot)
                if reading.snapshot is not None
                else None
            )
            response = CorridorInfoResponse(
                request_id=request.request_id,
                status=reading.status,
                age_ms=reading.age_ms,
                data=data,
                error=reading.error,
            )
            await websocket.send_json(response.model_dump(mode="json"))
    except WebSocketDisconnect:
        # Client chủ động ngắt kết nối là kết thúc bình thường của session.
        return
