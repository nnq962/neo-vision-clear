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
    """Tạo lifespan sở hữu monitor service nhưng chưa tự chạy runtime."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Công bố monitor service trong toàn bộ vòng đời application."""
        # Bước 1: tạo service và công bố qua app.state trước khi nhận request.
        service = monitor_factory(settings)
        app.state.monitor_service = service
        try:
            # Runtime tạm thời không tự khởi động cùng API server. API điều
            # khiển start/stop sẽ chủ động gọi service ở giai đoạn tiếp theo.
            yield
        finally:
            # Bước 2: dừng calibration đang chạy trước khi giải phóng monitor.
            calibration_service = getattr(app.state, "calibration_service", None)
            if calibration_service is not None:
                calibration_service.stop()

            # Bước 3: stop vẫn an toàn nếu runtime chưa từng được khởi động.
            service.stop()
            app.state.monitor_service = None

    return lifespan
