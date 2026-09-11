"""Route health-check phản ánh trạng thái snapshot camera."""

from typing import Annotated

from fastapi import APIRouter, Depends

from server.dependencies import get_monitor_service
from server.services.monitor import MonitorService
from server.settings import ServerSettings


router = APIRouter(tags=["health"])


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health")
def health(
    service: Annotated[MonitorService, Depends(get_monitor_service)],
) -> dict[str, object]:
    """Trả trạng thái worker và tuổi snapshot mới nhất."""
    # Dùng cùng ngưỡng stale với WebSocket để hai giao diện không mâu thuẫn.
    settings: ServerSettings = service.settings
    reading = service.snapshot_store.read(settings.snapshot_max_age_seconds)
    return {
        "status": reading.status,
        "age_ms": reading.age_ms,
        "error": reading.error,
    }
