"""Quản lý vòng đời tài nguyên nặng của FastAPI application."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.services.monitor import MonitorService
from server.settings import ServerSettings


MonitorFactory = Callable[[ServerSettings], MonitorService]


# ─────────────────────────────────────────────────────────────────────────────


def create_lifespan(
    settings: ServerSettings,
    monitor_factory: MonitorFactory = MonitorService,
):
    """Tạo lifespan khởi động và dừng monitor service cho một FastAPI app."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Sở hữu monitor service trong toàn bộ vòng đời application."""
        # Bước 1: tạo service và công bố qua app.state trước khi nhận request.
        service = monitor_factory(settings)
        app.state.monitor_service = service
        try:
            service.start()
            yield
        finally:
            # Bước 2: luôn dừng worker kể cả startup/request phát sinh lỗi.
            service.stop()
            app.state.monitor_service = None

    return lifespan
