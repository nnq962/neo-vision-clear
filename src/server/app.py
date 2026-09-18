"""Application factory của FastAPI server."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.lifespan import MonitorFactory, create_lifespan
from server.routes import (
    calibration_router,
    cameras_router,
    health_router,
    runtime_router,
    uart_router,
    websocket_router,
)
from server.services.calibration import CalibrationService
from server.services.camera_connection import CameraConnectionTester
from server.services.config_store import ConfigStore
from server.services.monitor import MonitorService
from server.services.uart import UartService
from server.settings import ServerSettings


# ─────────────────────────────────────────────────────────────────────────────


def create_app(
    settings: ServerSettings | None = None,
    monitor_factory: MonitorFactory = MonitorService,
    config_store: ConfigStore | None = None,
    camera_connection_tester: CameraConnectionTester | None = None,
    calibration_service: CalibrationService | None = None,
    uart_service: UartService | None = None,
) -> FastAPI:
    """Tạo FastAPI app với cấu hình và monitor factory có thể thay trong test."""
    # Bước 1: đọc và kiểm tra cấu hình trước khi dựng application.
    resolved_settings = settings or ServerSettings.from_env()
    resolved_settings.validate()

    # Bước 2: gắn lifespan và đăng ký các router transport độc lập.
    application = FastAPI(
        title="Neo Vision Clear Server",
        version="0.1.0",
        lifespan=create_lifespan(resolved_settings, monitor_factory),
    )
    resolved_config_store = config_store or ConfigStore(
        resolved_settings.camera_config_path,
    )
    application.state.config_store = resolved_config_store
    application.state.camera_connection_tester = (
        camera_connection_tester or CameraConnectionTester()
    )
    application.state.calibration_service = (
        calibration_service
        or CalibrationService(resolved_settings, resolved_config_store)
    )
    application.state.uart_service = uart_service or UartService(
        resolved_config_store,
        lambda: application.state.monitor_service.read_snapshot(),
    )
    application.include_router(cameras_router)
    application.include_router(calibration_router)
    application.include_router(health_router)
    application.include_router(runtime_router)
    application.include_router(uart_router)
    application.include_router(websocket_router)

    # Bước 3: đặt static frontend sau toàn bộ API và WebSocket để các route
    # nghiệp vụ luôn được ưu tiên trước mount bắt mọi đường dẫn còn lại.
    if resolved_settings.frontend_directory is not None:
        frontend_directory = Path(resolved_settings.frontend_directory)
        if frontend_directory.is_dir():
            application.mount(
                "/",
                StaticFiles(directory=frontend_directory, html=True),
                name="frontend",
            )
    return application


# Uvicorn có thể chạy trực tiếp bằng `uvicorn server.app:app`.
app = create_app()
