"""Kiểm tra nguồn camera trước khi lưu cấu hình."""

from __future__ import annotations

import time

from server.models.camera import CameraConfig, CameraCreate
from server.services.mediamtx import MediaMtxClient, MediaMtxError


class CameraConnectionError(RuntimeError):
    """Báo lỗi khi nguồn camera không mở hoặc không trả được frame."""


class CameraConnectionTester:
    """Đăng ký và xác nhận nguồn camera trên MediaMTX."""

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

    def register(self, path_name: str, camera: CameraCreate) -> None:
        """Đăng ký camera và giữ path khi MediaMTX báo sẵn sàng."""
        try:
            # Bước 1: thêm path mới rồi xác nhận nguồn thực sự có frame.
            self._client.add_source_path(path_name, camera.source)
            self._wait_until_ready(path_name)
        except MediaMtxError as exc:
            self._remove_quietly(path_name)
            raise CameraConnectionError(
                "Không thể kiểm tra camera qua MediaMTX."
            ) from exc
        except CameraConnectionError:
            # Bước 2: đăng ký lỗi phải rollback path vừa thêm.
            self._remove_quietly(path_name)
            raise

    # ─────────────────────────────────────────────────────────────────────────

    def restore(self, path_name: str, camera: CameraConfig) -> None:
        """Khôi phục path camera đã lưu sau khi MediaMTX khởi động lại."""
        try:
            # Bước 1: xóa cấu hình cũ nếu còn để thao tác có tính lặp lại.
            self._client.delete_path(path_name)

            # Bước 2: tạo lại path từ source đã lưu; MediaMTX sẽ tự kết nối lại.
            self._client.add_source_path(path_name, camera.source)
        except MediaMtxError as exc:
            raise CameraConnectionError(
                "Không thể khôi phục camera trên MediaMTX."
            ) from exc

    # ─────────────────────────────────────────────────────────────────────────

    def update(self, path_name: str, source: str, previous_source: str) -> None:
        """Đổi source và tự khôi phục source cũ nếu kết nối mới thất bại."""
        try:
            # Bước 1: cập nhật MediaMTX trước để không lưu một source chưa dùng được.
            self._client.update_source_path(path_name, source)
            self._wait_until_ready(path_name)
        except (MediaMtxError, CameraConnectionError) as exc:
            # Bước 2: rollback best-effort, nhưng vẫn trả nguyên lỗi của source mới.
            self._restore_source_quietly(path_name, previous_source)
            if isinstance(exc, MediaMtxError):
                raise CameraConnectionError(
                    "Không thể cập nhật camera qua MediaMTX."
                ) from exc
            raise

    # ─────────────────────────────────────────────────────────────────────────

    def remove(self, path_name: str) -> None:
        """Xóa path camera khỏi MediaMTX nếu đang tồn tại."""
        try:
            self._client.delete_path(path_name)
        except MediaMtxError as exc:
            raise CameraConnectionError(
                "Không thể xóa camera khỏi MediaMTX."
            ) from exc

    # ─────────────────────────────────────────────────────────────────────────

    def _wait_until_ready(self, path_name: str) -> None:
        """Chờ MediaMTX công bố path ở trạng thái sẵn sàng."""
        # Add hoặc patch thành công chưa đủ; path chỉ dùng được khi ready=true.
        for attempt in range(self._attempts):
            if attempt > 0:
                time.sleep(self._interval_seconds)
            status = self._client.get_path(path_name)
            if status is not None and status.get("ready") is True:
                return
        raise CameraConnectionError("MediaMTX không nhận được luồng camera.")

    # ─────────────────────────────────────────────────────────────────────────

    def _remove_quietly(self, path_name: str) -> None:
        """Dọn path tạm hoặc path đăng ký lỗi mà không che nguyên nhân chính."""
        # Bước 1: cleanup best-effort; caller vẫn nhận lỗi kết nối ban đầu.
        try:
            self._client.delete_path(path_name)
        except MediaMtxError:
            pass

    # ─────────────────────────────────────────────────────────────────────────

    def _restore_source_quietly(self, path_name: str, source: str) -> None:
        """Khôi phục source cũ mà không che lỗi cập nhật ban đầu."""
        # Rollback chỉ cần đưa cấu hình cũ trở lại; runtime sẽ tự kết nối lại.
        try:
            self._client.update_source_path(path_name, source)
        except MediaMtxError:
            pass
