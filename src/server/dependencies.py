"""Dependency truy cập các tài nguyên do FastAPI lifespan quản lý."""

from starlette.requests import HTTPConnection

from server.services.calibration import CalibrationService
from server.services.camera_connection import CameraConnectionTester
from server.services.config_store import ConfigStore
from server.services.monitor import MonitorService
from server.services.uart import UartService


# ─────────────────────────────────────────────────────────────────────────────


def get_monitor_service(connection: HTTPConnection) -> MonitorService:
    """Lấy monitor service đã được gắn vào app.state khi startup."""
    service = getattr(connection.app.state, "monitor_service", None)
    if service is None:
        raise RuntimeError("Monitor service chưa được lifespan khởi tạo.")
    return service


# ─────────────────────────────────────────────────────────────────────────────


def get_config_store(connection: HTTPConnection) -> ConfigStore:
    """Lấy kho cấu hình chung được gắn vào application state."""
    # Một store và một lock bảo vệ camera, baseline và runtime khỏi ghi đè nhau.
    store = getattr(connection.app.state, "config_store", None)
    if store is None:
        raise RuntimeError("Config store chưa được khởi tạo.")
    return store


# ─────────────────────────────────────────────────────────────────────────────


def get_calibration_service(connection: HTTPConnection) -> CalibrationService:
    """Lấy service chạy calibration headless của application."""
    # Service giữ job state trong process Uvicorn duy nhất.
    service = getattr(connection.app.state, "calibration_service", None)
    if service is None:
        raise RuntimeError("Calibration service chưa được khởi tạo.")
    return service


# ─────────────────────────────────────────────────────────────────────────────


def get_camera_connection_tester(
    connection: HTTPConnection,
) -> CameraConnectionTester:
    """Lấy service kiểm tra camera được gắn vào application state."""
    # Một instance không giữ kết nối được dùng chung cho các request tuần tự.
    tester = getattr(connection.app.state, "camera_connection_tester", None)
    if tester is None:
        raise RuntimeError("Camera connection tester chưa được khởi tạo.")
    return tester


# ─────────────────────────────────────────────────────────────────────────────


def get_uart_service(connection: HTTPConnection) -> UartService:
    """Lấy UART service độc lập được gắn vào application state."""
    service = getattr(connection.app.state, "uart_service", None)
    if service is None:
        raise RuntimeError("UART service chưa được khởi tạo.")
    return service
