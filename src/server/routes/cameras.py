"""REST API quản lý cấu hình camera."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status

from server.dependencies import get_camera_connection_tester, get_config_store
from server.models.camera import CameraCreate, CameraResponse, CameraUpdate
from server.services.camera_connection import (
    CameraConnectionError,
    CameraConnectionTester,
)
from server.services.config_store import (
    CameraNotFoundError,
    CameraValidationError,
    ConfigStore,
)


router = APIRouter(prefix="/api/cameras", tags=["cameras"])


# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[CameraResponse])
def list_cameras(
    store: Annotated[ConfigStore, Depends(get_config_store)],
) -> list[CameraResponse]:
    """Trả toàn bộ camera mà không công bố mật khẩu."""
    # Chuyển từng bản ghi nội bộ thành schema công khai.
    return [camera.to_response() for camera in store.list_cameras()]


# ─────────────────────────────────────────────────────────────────────────────


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
def create_camera(
    payload: CameraCreate,
    store: Annotated[ConfigStore, Depends(get_config_store)],
    tester: Annotated[
        CameraConnectionTester,
        Depends(get_camera_connection_tester),
    ],
) -> CameraResponse:
    """Đăng ký MediaMTX rồi lưu camera khi path đã sẵn sàng."""
    # Ghi nhớ path cũ để dọn sau khi camera mới đã sẵn sàng và lưu thành công.
    current_cameras = store.list_cameras()
    current_camera = current_cameras[0] if current_cameras else None

    # ID dùng chung cho JSON và path WebRTC của MediaMTX.
    camera_id = uuid4().hex[:12]
    try:
        tester.register(camera_id, payload)
    except CameraConnectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        camera = store.create_camera(payload, camera_id=camera_id)
    except Exception:
        # JSON không ghi được thì rollback path để hai hệ thống không lệch nhau.
        tester.remove(camera_id)
        raise
    if current_camera is not None and current_camera.id != camera_id:
        try:
            tester.remove(current_camera.id)
        except CameraConnectionError:
            # Camera mới đã lưu thành công; path cũ không được làm request thất bại.
            pass
    return camera.to_response()


# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{camera_id}", response_model=CameraResponse)
def get_camera(
    camera_id: str,
    store: Annotated[ConfigStore, Depends(get_config_store)],
) -> CameraResponse:
    """Trả một camera theo ID mà không công bố mật khẩu."""
    try:
        return store.get_camera(camera_id).to_response()
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────


@router.patch("/{camera_id}", response_model=CameraResponse)
def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    store: Annotated[ConfigStore, Depends(get_config_store)],
) -> CameraResponse:
    """Cập nhật từng phần một cấu hình camera."""
    try:
        return store.update_camera(camera_id, payload).to_response()
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CameraValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ─────────────────────────────────────────────────────────────────────────────


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    camera_id: str,
    store: Annotated[ConfigStore, Depends(get_config_store)],
    tester: Annotated[
        CameraConnectionTester,
        Depends(get_camera_connection_tester),
    ],
) -> Response:
    """Xóa một cấu hình camera và trả response không có nội dung."""
    try:
        store.get_camera(camera_id)
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        tester.remove(camera_id)
    except CameraConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    store.delete_camera(camera_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
