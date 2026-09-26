"""FastAPI nhận kết quả camera và phát quyết định tổng hợp qua WebSocket."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import re
from typing import List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from neo_vision_clear_aggregator.config import (
    AggregatorConfig,
    AggregatorConfigError,
    load_config,
    save_config,
)
from neo_vision_clear_aggregator.models import (
    CameraMeasurement,
    CameraStatus,
    CorridorDecision,
    DashboardResponse,
    HealthResponse,
    LatestPayloadResponse,
    OutboundStatus,
    SourceStatus,
)
from neo_vision_clear_aggregator.outbound import OutboundPublisher
from neo_vision_clear_aggregator.registry import (
    SourceMismatchError,
    SourceRegistry,
    UnknownCameraError,
)
from neo_vision_clear_aggregator.settings import AggregatorSettings


SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
STATIC_DIRECTORY = Path(__file__).resolve().parent / "static"


def create_app(
    settings: Optional[AggregatorSettings] = None,
    config: Optional[AggregatorConfig] = None,
) -> FastAPI:
    """Tạo Aggregator app với config có thể thay thế trong kiểm thử."""
    resolved_settings = settings or AggregatorSettings.from_env()
    resolved_settings.validate()
    resolved_config = config or load_config(resolved_settings.config_path)
    registry = SourceRegistry(
        resolved_config,
        resolved_settings.source_stale_seconds,
    )
    outbound = OutboundPublisher(resolved_config.outbound)
    config_update_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        """Chạy publisher outbound và watcher chuyển trạng thái stale."""
        outbound.start()
        watcher = asyncio.create_task(
            _watch_stale_decision(registry, outbound),
            name="aggregator-stale-watcher",
        )
        try:
            yield
        finally:
            watcher.cancel()
            try:
                await watcher
            except asyncio.CancelledError:
                pass
            await outbound.close()

    application = FastAPI(
        title="Neo Vision Clear Aggregator",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.config = resolved_config
    application.state.registry = registry
    application.state.outbound = outbound

    @application.get("/", include_in_schema=False)
    async def dashboard_page() -> FileResponse:
        """Phục vụ dashboard cấu hình và quan sát Aggregator."""
        return FileResponse(STATIC_DIRECTORY / "index.html")

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Trả trạng thái nhẹ cho Docker và bộ giám sát."""
        return await registry.health()

    @application.get("/api/sources", response_model=List[SourceStatus])
    async def list_sources() -> List[SourceStatus]:
        """Liệt kê các Jetson đã từng kết nối cùng độ mới message cuối."""
        return await registry.list_sources()

    @application.get("/api/cameras", response_model=List[CameraStatus])
    async def list_cameras() -> List[CameraStatus]:
        """Liệt kê mọi camera cấu hình theo thứ tự vật lý của hành lang."""
        return await registry.list_cameras()

    @application.get("/api/decision", response_model=CorridorDecision)
    async def corridor_decision() -> CorridorDecision:
        """Trả quyết định tổng hợp hiện tại để vận hành và chẩn đoán."""
        return await registry.decision()

    @application.get("/api/outbound", response_model=OutboundStatus)
    async def outbound_status() -> OutboundStatus:
        """Trả trạng thái kết nối và lần gửi gần nhất tới server đích."""
        return outbound.status()

    @application.get("/api/dashboard", response_model=DashboardResponse)
    async def dashboard_status() -> DashboardResponse:
        """Gom trạng thái dashboard trong một request gọn nhẹ."""
        # Bước 1: các phép đọc độc lập chạy đồng thời trên cùng event loop.
        health_data, sources, cameras, decision, latest = await asyncio.gather(
            registry.health(),
            registry.list_sources(),
            registry.list_cameras(),
            registry.decision(),
            registry.list_latest(),
        )
        return DashboardResponse(
            health=health_data,
            sources=sources,
            cameras=cameras,
            decision=decision,
            latest_received=latest,
            outbound=outbound.status(),
        )

    @application.get("/api/config", response_model=AggregatorConfig)
    async def get_config() -> AggregatorConfig:
        """Trả cấu hình đang áp dụng để frontend dựng biểu mẫu."""
        return application.state.config.model_copy(deep=True)

    @application.put("/api/config", response_model=AggregatorConfig)
    async def update_config(payload: AggregatorConfig) -> AggregatorConfig:
        """Lưu và áp dụng cấu hình mới mà không restart process."""
        async with config_update_lock:
            try:
                # Bước 1: ghi bền vững trước, chỉ áp dụng khi file lưu thành công.
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    save_config,
                    resolved_settings.config_path,
                    payload,
                )
            except AggregatorConfigError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc

            # Bước 2: registry và outbound cùng chuyển sang một phiên bản config.
            await registry.update_config(payload)
            await outbound.reconfigure(payload.outbound)
            application.state.config = payload.model_copy(deep=True)
            await outbound.publish(await registry.decision())
            return payload.model_copy(deep=True)

    @application.get(
        "/api/sources/{source_id}/latest",
        response_model=LatestPayloadResponse,
    )
    async def latest_payload(source_id: str) -> LatestPayloadResponse:
        """Đọc payload hợp lệ cuối cùng của một Jetson."""
        result = await registry.latest(source_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Source '{source_id}' chưa có payload.",
            )
        return result

    @application.websocket("/ws/ingest/{source_id}")
    async def ingest(websocket: WebSocket, source_id: str) -> None:
        """Nhận message camera một chiều và phát quyết định mới tới server."""
        await websocket.accept()
        if SOURCE_ID_PATTERN.fullmatch(source_id) is None:
            await websocket.close(code=1008, reason="source_id invalid")
            return

        await registry.connect(source_id)
        try:
            while True:
                try:
                    # Bước 1: chỉ nhận JSON object đúng schema đã chốt.
                    raw_payload = await websocket.receive_json()
                    payload = CameraMeasurement.model_validate(raw_payload)
                    decision = await registry.ingest(source_id, payload)
                except (json.JSONDecodeError, UnicodeDecodeError, ValidationError):
                    await websocket.close(code=1008, reason="invalid payload")
                    return
                except (UnknownCameraError, SourceMismatchError) as exc:
                    await websocket.close(code=1008, reason=str(exc)[:120])
                    return

                # Bước 2: outbound queue latest-wins nên không làm nghẽn ingest.
                await outbound.publish(decision)
        except WebSocketDisconnect:
            return
        finally:
            await registry.disconnect(source_id)

    application.mount(
        "/static",
        StaticFiles(directory=STATIC_DIRECTORY),
        name="aggregator-static",
    )

    return application


# ─────────────────────────────────────────────────────────────────────────────


async def _watch_stale_decision(
    registry: SourceRegistry,
    outbound: OutboundPublisher,
) -> None:
    """Phát lại khi camera chuyển stale dù không còn message mới đến."""
    previous_fingerprint = None
    while True:
        # Bước 1: nửa giây đủ nhanh so với ngưỡng stale mặc định ba giây.
        await asyncio.sleep(0.5)
        decision = await registry.decision()
        fingerprint = decision.model_dump(mode="json", exclude={"decided_at"})
        if fingerprint != previous_fingerprint:
            previous_fingerprint = fingerprint
            await outbound.publish(decision)


app = create_app()
