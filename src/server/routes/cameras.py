"""REST API quản lý cấu hình camera."""

from __future__ import annotations

from typing import List

from typing_extensions import Annotated
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


@router.get("", response_model=List[CameraResponse])
def list_cameras(
    store: Annotated[ConfigStore, Depends(get_config_store)],
) -> list[CameraResponse]:
    """Trả camera singleton hiện tại dưới dạng danh sách tương thích API."""
    # Response giữ source để form có thể chỉnh sửa cấu hình camera hiện tại.
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
    current_camera = store.get_current_camera()

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
    """Trả cấu hình camera theo ID để frontend chỉnh sửa."""
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
    tester: Annotated[
        CameraConnectionTester,
        Depends(get_camera_connection_tester),
    ],
) -> CameraResponse:
    """Cập nhật camera đồng bộ giữa MediaMTX và tệp cấu hình."""
    try:
        # Bước 1: chỉ kết nối lại MediaMTX khi URL nguồn thực sự thay đổi.
        current_camera = store.get_camera(camera_id)
        source_changed = (
            payload.source is not None and payload.source != current_camera.source
        )
        if source_changed:
            tester.update(camera_id, payload.source, current_camera.source)

        # Bước 2: MediaMTX đã chấp nhận source thì mới ghi JSON.
        try:
            updated = store.update_camera(camera_id, payload)
        except Exception:
            if source_changed:
                # JSON lỗi phải đưa MediaMTX về source cũ để tránh lệch trạng thái.
                try:
                    tester.update(camera_id, current_camera.source, payload.source)
                except CameraConnectionError:
                    pass
            raise
        return updated.to_response()
    except CameraNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (CameraConnectionError, CameraValidationError) as exc:
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
