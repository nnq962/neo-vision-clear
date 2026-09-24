"""WebSocket request-response cung cấp snapshot hành lang mới nhất."""

from __future__ import annotations

import json
from typing_extensions import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from server.dependencies import get_monitor_service
from server.models.messages import (
    CorridorInfoData,
    CorridorInfoRequest,
    CorridorInfoResponse,
    OverviewCameraInfo,
    OverviewInfoData,
    OverviewInfoRequest,
    OverviewInfoResponse,
    ProtocolErrorResponse,
    SnapshotRequest,
    SnapshotResponse,
)
from server.services.monitor import MonitorService


router = APIRouter(tags=["websocket"])


# ─────────────────────────────────────────────────────────────────────────────


def _request_id_from_payload(payload: object) -> str | None:
    """Lấy request ID an toàn từ message chưa được Pydantic xác thực."""
    # Bước 1: chỉ phản chiếu chuỗi hợp lệ để response lỗi không mang object lạ.
    if not isinstance(payload, dict):
        return None
    request_id = payload.get("request_id")
    return request_id if isinstance(request_id, str) else None


# ─────────────────────────────────────────────────────────────────────────────


async def _serve_snapshots(
    websocket: WebSocket,
    service: MonitorService,
    request_model: type[SnapshotRequest],
    response_model: type[SnapshotResponse],
    include_zones: bool,
) -> None:
    """Phục vụ vòng lặp protocol chung cho mọi loại snapshot WebSocket."""
    await websocket.accept()
    try:
        while True:
            # Bước 1: xác thực message và giữ kết nối mở khi client gửi sai.
            payload = None
            try:
                payload = await websocket.receive_json()
                request = request_model.model_validate(payload)
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                response = ProtocolErrorResponse(
                    request_id=_request_id_from_payload(payload),
                    error=str(exc),
                )
                await websocket.send_json(response.model_dump(mode="json"))
                continue

            # Bước 2: đọc snapshot đúng một lần để data, zone và age đồng bộ.
            reading = service.read_snapshot()
            data = None
            if reading.snapshot is not None:
                data = (
                    OverviewInfoData.from_snapshot(
                        reading.snapshot,
                        reading.difference_zones,
                    )
                    if include_zones
                    else CorridorInfoData.from_snapshot(reading.snapshot)
                )
            response = response_model(
                request_id=request.request_id,
                status=reading.status,
                age_ms=reading.age_ms,
                data=data,
                error=reading.error,
            )
            await websocket.send_json(response.model_dump(mode="json"))
    except WebSocketDisconnect:
        # Client rời trang hoặc đóng kết nối là kết thúc bình thường của session.
        return


# ─────────────────────────────────────────────────────────────────────────────


@router.websocket("/ws/corridor")
async def corridor_websocket(
    websocket: WebSocket,
    service: Annotated[MonitorService, Depends(get_monitor_service)],
) -> None:
    """Trả snapshot phép đo gọn nhẹ cho robot trên kết nối WebSocket."""
    await _serve_snapshots(
        websocket,
        service,
        CorridorInfoRequest,
        CorridorInfoResponse,
        include_zones=False,
    )


# ─────────────────────────────────────────────────────────────────────────────


@router.websocket("/ws/overview")
async def overview_websocket(
    websocket: WebSocket,
    service: Annotated[MonitorService, Depends(get_monitor_service)],
) -> None:
    """Trả snapshot kèm polygon của mọi camera runtime cho dashboard."""
    await websocket.accept()
    try:
        while True:
            # Bước 1: xác thực request và giữ socket mở nếu client gửi sai.
            payload = None
            try:
                payload = await websocket.receive_json()
                request = OverviewInfoRequest.model_validate(payload)
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                response = ProtocolErrorResponse(
                    request_id=_request_id_from_payload(payload),
                    error=str(exc),
                )
                await websocket.send_json(response.model_dump(mode="json"))
                continue

            # Bước 2: đóng gói từng camera độc lập trong cùng một response.
            items = []
            for baseline_id, reading in service.read_overview_snapshots():
                data = (
                    OverviewInfoData.from_snapshot(
                        reading.snapshot,
                        reading.difference_zones,
                    )
                    if reading.snapshot is not None
                    else None
                )
                items.append(
                    OverviewCameraInfo(
                        baseline_id=baseline_id,
                        status=reading.status,
                        age_ms=reading.age_ms,
                        error=reading.error,
                        data=data,
                    )
                )
            response = OverviewInfoResponse(
                request_id=request.request_id,
                items=items,
            )
            await websocket.send_json(response.model_dump(mode="json"))
    except WebSocketDisconnect:
        # Client rời trang hoặc đóng kết nối là kết thúc bình thường.
        return
