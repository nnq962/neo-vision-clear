"""REST API telemetry CPU/GPU/RAM của máy đang chạy FastAPI."""

from typing_extensions import Annotated

from fastapi import APIRouter, Depends

from server.dependencies import get_system_metrics_service
from server.models.system_metrics import SystemMetricsResponse
from server.services.system_metrics import SystemMetricsService


router = APIRouter(prefix="/api/system", tags=["system"])


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/metrics", response_model=SystemMetricsResponse)
def get_system_metrics(
    service: Annotated[SystemMetricsService, Depends(get_system_metrics_service)],
) -> SystemMetricsResponse:
    """Trả mẫu CPU/GPU/RAM, không phụ thuộc trạng thái runtime camera."""
    # Bước 1: service tự xử lý cảm biến thiếu bằng giá trị null.
    return service.read()
