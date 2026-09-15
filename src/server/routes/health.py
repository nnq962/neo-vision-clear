"""Route health-check phản ánh trạng thái snapshot camera."""

from typing import Annotated

from fastapi import APIRouter, Depends

from server.dependencies import get_monitor_service
from server.services.monitor import MonitorService


router = APIRouter(tags=["health"])


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health")
def health(
    service: Annotated[MonitorService, Depends(get_monitor_service)],
) -> dict[str, object]:
    """Trả trạng thái worker và tuổi snapshot mới nhất."""
    # Dùng ngưỡng của phiên runtime hiện tại để khớp cấu hình JSON đã lưu.
    reading = service.read_snapshot()
    return {
        "status": reading.status,
        "age_ms": reading.age_ms,
        "error": reading.error,
    }
