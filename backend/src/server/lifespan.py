"""Quản lý vòng đời tài nguyên nặng của FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI

from server.services.camera_connection import CameraConnectionError
from server.services.monitor import MonitorService
from server.settings import ServerSettings
from utils.logger import LOGGER


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
        aggregator_publisher = getattr(app.state, "aggregator_publisher", None)
        if aggregator_publisher is not None:
            # Bước 2: callback không chặn cho phép worker đẩy ngay mỗi kết quả.
            if hasattr(service, "set_output_publisher"):
                service.set_output_publisher(aggregator_publisher.publish)
            aggregator_publisher.start()

        # Bước 3: MediaMTX không lưu path động sau restart, nên khôi phục toàn bộ
        # camera từ config trước khi frontend tạo các player.
        for camera in app.state.config_store.list_cameras():
            try:
                app.state.camera_connection_tester.restore(camera.id, camera)
                LOGGER.info(
                    "Đã khôi phục MediaMTX path cho camera %s.",
                    camera.id,
                )
            except CameraConnectionError as exc:
                # API vẫn phải hoạt động để người dùng sửa camera hoặc hạ tầng.
                LOGGER.warning(
                    "Chưa khôi phục được MediaMTX path cho camera %s: %s",
                    camera.id,
                    exc,
                )

        # Bước 4: UART là hạ tầng tùy chọn; lỗi port không được chặn FastAPI.
        uart_service = getattr(app.state, "uart_service", None)
        if uart_service is not None:
            try:
                uart_service.start()
            except Exception as exc:
                LOGGER.warning("UART chưa sẵn sàng khi startup: %s", exc)
        try:
            # Runtime tạm thời không tự khởi động cùng API server. API điều
            # khiển start/stop sẽ chủ động gọi service ở giai đoạn tiếp theo.
            yield
        finally:
            # Bước 5: dừng calibration đang chạy trước khi giải phóng monitor.
            calibration_service = getattr(app.state, "calibration_service", None)
            if calibration_service is not None:
                calibration_service.stop()

            # Bước 6: đóng UART độc lập, kể cả khi chưa từng kết nối thành công.
            if uart_service is not None:
                try:
                    uart_service.close()
                except Exception as exc:
                    LOGGER.warning("Không thể đóng UART hoàn toàn: %s", exc)

            # Bước 7: stop vẫn an toàn nếu runtime chưa từng được khởi động.
            service.stop()
            if aggregator_publisher is not None:
                aggregator_publisher.close()
            app.state.monitor_service = None

    return lifespan
