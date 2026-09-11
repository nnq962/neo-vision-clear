"""Application factory của FastAPI server."""

from __future__ import annotations

from fastapi import FastAPI

from server.lifespan import MonitorFactory, create_lifespan
from server.routes import health_router, websocket_router
from server.services.monitor import MonitorService
from server.settings import ServerSettings


# ─────────────────────────────────────────────────────────────────────────────


def create_app(
    settings: ServerSettings | None = None,
    monitor_factory: MonitorFactory = MonitorService,
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
    application.include_router(health_router)
    application.include_router(websocket_router)
    return application


# Uvicorn có thể chạy trực tiếp bằng `uvicorn server.app:app`.
app = create_app()
