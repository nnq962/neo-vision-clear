"""REST API đọc và cập nhật cấu hình runtime detection."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from server.dependencies import get_config_store, get_monitor_service
from server.models.config import RuntimeConfig, RuntimeProcessResponse
from server.services.config_store import ConfigStore, RuntimeValidationError
from server.services.monitor import (
    MonitorService,
    RuntimeBusyError,
    RuntimeStartError,
)


router = APIRouter(prefix="/api/runtime", tags=["runtime"])


# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_model=RuntimeConfig)
def get_runtime_config(
    store: Annotated[ConfigStore, Depends(get_config_store)],
) -> RuntimeConfig:
    """Trả cấu hình runtime hiện tại mà không khởi động worker."""
    # Bước 1: ConfigStore trả default đầy đủ cả khi chưa có tệp JSON.
    return store.get_runtime()


# ─────────────────────────────────────────────────────────────────────────────


@router.put("", response_model=RuntimeConfig)
def update_runtime_config(
    payload: RuntimeConfig,
    store: Annotated[ConfigStore, Depends(get_config_store)],
) -> RuntimeConfig:
    """Thay thế cấu hình runtime sau khi kiểm tra camera và baseline."""
    try:
        # Bước 1: lưu toàn bộ object để tránh trộn tham số cũ và mới ngoài ý muốn.
        return store.update_runtime(payload)
    except RuntimeValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/status", response_model=RuntimeProcessResponse)
def get_runtime_status(
    service: Annotated[MonitorService, Depends(get_monitor_service)],
) -> RuntimeProcessResponse:
    """Trả trạng thái thực tế của worker mà không thay đổi cấu hình."""
    # Bước 1: response là snapshot thread-safe của state runtime hiện tại.
    return service.status()


# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/start",
    response_model=RuntimeProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_runtime(
    store: Annotated[ConfigStore, Depends(get_config_store)],
    service: Annotated[MonitorService, Depends(get_monitor_service)],
) -> RuntimeProcessResponse:
    """Khởi động worker nền từ camera, baseline và runtime config đã lưu."""
    # Bước 1: resolve toàn bộ tham chiếu trước khi thay đổi trạng thái worker.
    runtime = store.get_runtime()
    baseline_id = runtime.active_baseline_id
    if baseline_id is None:
        raise HTTPException(
            status_code=409,
            detail="Cần chọn active_baseline_id trước khi chạy runtime.",
        )
    cameras = store.list_cameras()
    if not cameras:
        raise HTTPException(status_code=409, detail="Chưa có camera để chạy runtime.")
    try:
        baseline = store.get_baseline(baseline_id)
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Bước 2: enabled phản ánh lệnh chạy gần nhất trong cấu hình bền vững.
    enabled_runtime = runtime.model_copy(update={"enabled": True})
    try:
        store.update_runtime(enabled_runtime)
        return service.start(cameras[0], baseline, enabled_runtime)
    except (RuntimeBusyError, RuntimeStartError) as exc:
        # Hoàn tác cờ enabled nếu worker không nhận được lệnh start.
        store.update_runtime(runtime)
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/stop",
    response_model=RuntimeProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def stop_runtime(
    store: Annotated[ConfigStore, Depends(get_config_store)],
    service: Annotated[MonitorService, Depends(get_monitor_service)],
) -> RuntimeProcessResponse:
    """Phát tín hiệu dừng worker và trả ngay, không chờ camera đóng xong."""
    # Bước 1: lưu trạng thái mong muốn trước để lần đọc config kế tiếp nhất quán.
    runtime = store.get_runtime()
    store.update_runtime(runtime.model_copy(update={"enabled": False}))

    # Bước 2: wait=False giữ request nhanh dù camera đang block theo timeout.
    return service.stop(wait=False)
