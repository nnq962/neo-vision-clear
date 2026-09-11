"""Các route HTTP và WebSocket của server."""

from server.routes.health import router as health_router
from server.routes.websocket import router as websocket_router

__all__ = ["health_router", "websocket_router"]
