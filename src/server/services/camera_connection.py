"""Kiểm tra nguồn camera trước khi lưu cấu hình."""

from __future__ import annotations

import time
from uuid import uuid4

from server.models.camera import CameraCreate
from server.services.mediamtx import MediaMtxClient, MediaMtxError


class CameraConnectionError(RuntimeError):
    """Báo lỗi khi nguồn camera không mở hoặc không trả được frame."""


class CameraConnectionTester:
    """Dùng path tạm trên MediaMTX để xác nhận camera dùng được."""

    def __init__(
        self,
        client: MediaMtxClient | None = None,
        attempts: int = 12,
        interval_seconds: float = 0.5,
    ):
        """Khởi tạo tester với client và chính sách chờ path ready."""
        self._client = client or MediaMtxClient()
        self._attempts = attempts
        self._interval_seconds = interval_seconds

    # ─────────────────────────────────────────────────────────────────────────

    def validate(self, camera: CameraCreate) -> None:
        """Yêu cầu MediaMTX kéo source và báo path ready trước khi trả về."""
        # Bước 1: path ngẫu nhiên tránh đụng cấu hình camera đã hoạt động.
        source = camera.source
        path_name = f"probe-{uuid4().hex}"
        added = False
        try:
            self._client.add_source_path(path_name, source)
            added = True

            # Bước 2: add config thành công chưa đủ; chỉ ready=true mới chứng
            # minh MediaMTX đã nhận được track từ camera.
            for attempt in range(self._attempts):
                if attempt > 0:
                    time.sleep(self._interval_seconds)
                status = self._client.get_path(path_name)
                if status is not None and status.get("ready") is True:
                    return
            raise CameraConnectionError("MediaMTX không nhận được luồng camera.")
        except CameraConnectionError:
            raise
        except MediaMtxError as exc:
            raise CameraConnectionError(
                "Không thể kiểm tra camera qua MediaMTX."
            ) from exc
        finally:
            # Bước 3: luôn xóa path probe, kể cả khi camera không hợp lệ.
            if added:
                try:
                    self._client.delete_path(path_name)
                except MediaMtxError:
                    pass

    # ─────────────────────────────────────────────────────────────────────────

    def register(self, path_name: str, camera: CameraCreate) -> None:
        """Đăng ký camera và giữ path khi MediaMTX báo sẵn sàng."""
        added = False
        ready = False
        try:
            self._client.add_source_path(path_name, camera.source)
            added = True
            for attempt in range(self._attempts):
                if attempt > 0:
                    time.sleep(self._interval_seconds)
                status = self._client.get_path(path_name)
                if status is not None and status.get("ready") is True:
                    ready = True
                    return
            raise CameraConnectionError("MediaMTX không nhận được luồng camera.")
        except CameraConnectionError:
            raise
        except MediaMtxError as exc:
            raise CameraConnectionError(
                "Không thể kiểm tra camera qua MediaMTX."
            ) from exc
        finally:
            # Chỉ rollback path khi đăng ký không hoàn tất.
            if added and not ready:
                try:
                    self._client.delete_path(path_name)
                except MediaMtxError:
                    pass

    # ─────────────────────────────────────────────────────────────────────────

    def remove(self, path_name: str) -> None:
        """Xóa path camera khỏi MediaMTX nếu đang tồn tại."""
        try:
            self._client.delete_path(path_name)
        except MediaMtxError as exc:
            raise CameraConnectionError(
                "Không thể xóa camera khỏi MediaMTX."
            ) from exc
