"""REST API đọc và lưu cấu hình calibration."""

from __future__ import annotations

from typing import List

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse

from server.dependencies import get_calibration_service, get_config_store
from server.models.calibration import (
    CalibrationCreate,
    CalibrationCreateRequest,
    CalibrationResponse,
    CalibrationRunResponse,
    CalibrationUpdate,
)
from server.services.calibration import (
    CalibrationArtifactNotFoundError,
    CalibrationBusyError,
    CalibrationCameraError,
    CalibrationService,
)
from server.services.config_store import (
    BaselineNameConflictError,
    BaselineNotFoundError,
    CameraNotFoundError,
    ConfigStore,
)


router = APIRouter(prefix="/api/calibration", tags=["calibration"])


# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_model=List[CalibrationResponse])
def list_baselines(
    store: Annotated[ConfigStore, Depends(get_config_store)],
    camera_id: str | None = None,
) -> list[CalibrationResponse]:
    """Trả baseline của một camera hoặc toàn bộ baseline đã lưu."""
    # Bước 1: lọc theo camera khi frontend đang cấu hình một nguồn cụ thể.
    baselines = store.list_baselines()
    if camera_id is not None:
        baselines = [item for item in baselines if item.camera_id == camera_id]
    return [baseline.to_response() for baseline in baselines]


# ─────────────────────────────────────────────────────────────────────────────


@router.post("", response_model=CalibrationResponse, status_code=status.HTTP_201_CREATED)
def create_baseline(
    payload: CalibrationCreateRequest,
    store: Annotated[ConfigStore, Depends(get_config_store)],
) -> CalibrationResponse:
    """Validate và thêm baseline mới mà không khởi chạy calibration."""
    # Bước 1: camera phải được chỉ định rõ, không tự chọn nguồn đầu tiên.
    try:
        camera = store.get_camera(payload.camera_id)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Bước 2: loại camera_id khỏi các trường cấu hình trước khi ghi document.
    create_payload = CalibrationCreate.model_validate(
        payload.model_dump(exclude={"camera_id"})
    )
    try:
        return store.create_baseline(camera.id, create_payload).to_response()
    except BaselineNameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{baseline_id}", response_model=CalibrationResponse)
def get_baseline(
    baseline_id: str,
    store: Annotated[ConfigStore, Depends(get_config_store)],
) -> CalibrationResponse:
    """Trả một baseline theo ID mà không chạy pipeline."""
    try:
        # Bước 1: lấy bản ghi độc lập để frontend nạp lại form.
        return store.get_baseline(baseline_id).to_response()
    except BaselineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{baseline_id}/run",
    response_model=CalibrationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_baseline_calibration(
    baseline_id: str,
    service: Annotated[CalibrationService, Depends(get_calibration_service)],
) -> CalibrationRunResponse:
    """Khởi động tạo artifact baseline trong worker headless."""
    try:
        # Bước 1: service xác thực baseline, camera và quyền sở hữu worker.
        return service.start(baseline_id)
    except BaselineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CalibrationCameraError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CalibrationBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{baseline_id}/status",
    response_model=CalibrationRunResponse,
)
def get_baseline_calibration_status(
    baseline_id: str,
    service: Annotated[CalibrationService, Depends(get_calibration_service)],
) -> CalibrationRunResponse:
    """Trả tiến độ hoặc kết quả calibration của một baseline."""
    try:
        # Bước 1: đọc state thread-safe mà không chờ worker hoàn tất.
        return service.status(baseline_id)
    except BaselineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{baseline_id}/images/{image_type}", response_class=FileResponse)
def get_baseline_image(
    baseline_id: str,
    image_type: str,
    store: Annotated[ConfigStore, Depends(get_config_store)],
    service: Annotated[CalibrationService, Depends(get_calibration_service)],
) -> FileResponse:
    """Trả ảnh RGB preview hoặc heatmap depth của một baseline."""
    try:
        # Bước 1: không cho truy cập artifact không còn bản ghi cấu hình.
        store.get_baseline(baseline_id)

        # Bước 2: service tìm ảnh trong thư mục artifact của baseline.
        image_path = service.get_artifact_image_path(baseline_id, image_type)
    except BaselineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CalibrationArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(image_path, media_type="image/jpeg")


# ─────────────────────────────────────────────────────────────────────────────


@router.put("/{baseline_id}", response_model=CalibrationResponse)
def update_baseline(
    baseline_id: str,
    payload: CalibrationUpdate,
    store: Annotated[ConfigStore, Depends(get_config_store)],
) -> CalibrationResponse:
    """Thay thế cấu hình của một baseline mà không chạy pipeline."""
    try:
        # Bước 1: chỉ cập nhật JSON; camera và model không được mở tại đây.
        return store.update_baseline(baseline_id, payload).to_response()
    except BaselineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BaselineNameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────


@router.delete("/{baseline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_baseline(
    baseline_id: str,
    store: Annotated[ConfigStore, Depends(get_config_store)],
    service: Annotated[CalibrationService, Depends(get_calibration_service)],
) -> Response:
    """Xóa cấu hình cùng toàn bộ artifact của đúng một baseline."""
    try:
        # Bước 1: xác thực ID trước khi thực hiện thay đổi trên filesystem.
        store.get_baseline(baseline_id)

        # Bước 2: dọn artifact trước; nếu thất bại thì vẫn giữ cấu hình để thử lại.
        service.delete_artifacts(baseline_id)

        # Bước 3: chỉ xóa cấu hình sau khi filesystem đã được dọn thành công.
        store.delete_baseline(baseline_id)
    except BaselineNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CalibrationBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
