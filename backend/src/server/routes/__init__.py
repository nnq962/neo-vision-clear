"""Các route HTTP và WebSocket của server."""

from server.routes.calibration import router as calibration_router
from server.routes.cameras import router as cameras_router
from server.routes.health import router as health_router
from server.routes.runtime import router as runtime_router
from server.routes.system_metrics import router as system_metrics_router
from server.routes.uart import router as uart_router
from server.routes.websocket import router as websocket_router

__all__ = [
    "calibration_router",
    "cameras_router",
    "health_router",
    "runtime_router",
    "system_metrics_router",
    "uart_router",
    "websocket_router",
]
