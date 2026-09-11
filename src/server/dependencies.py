"""Dependency truy cập các tài nguyên do FastAPI lifespan quản lý."""

from starlette.requests import HTTPConnection

from server.services.monitor import MonitorService


# ─────────────────────────────────────────────────────────────────────────────


def get_monitor_service(connection: HTTPConnection) -> MonitorService:
    """Lấy monitor service đã được gắn vào app.state khi startup."""
    service = getattr(connection.app.state, "monitor_service", None)
    if service is None:
        raise RuntimeError("Monitor service chưa được lifespan khởi tạo.")
    return service
