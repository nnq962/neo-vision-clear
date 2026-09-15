"""Client nhỏ gọi MediaMTX Control API cho nghiệp vụ camera."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class MediaMtxError(RuntimeError):
    """Báo lỗi khi MediaMTX từ chối request hoặc không thể kết nối."""

    def __init__(self, message: str, status_code: int | None = None):
        """Lưu thông báo an toàn và HTTP status từ MediaMTX nếu có."""
        super().__init__(message)
        self.status_code = status_code


class MediaMtxClient:
    """Cung cấp các thao tác path tối thiểu trên MediaMTX API v3."""

    def __init__(self, api_url: str | None = None, timeout_seconds: float = 5.0):
        """Khởi tạo client từ URL truyền vào hoặc biến môi trường."""
        # URL mặc định chỉ gọi MediaMTX trên cùng host với backend.
        self.api_url = (
            api_url
            or os.getenv("MEDIAMTX_API_URL", "http://127.0.0.1:9997/v3")
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds

    # ─────────────────────────────────────────────────────────────────────────

    def add_source_path(self, path_name: str, source: str) -> None:
        """Thêm path kéo source ngay để MediaMTX kiểm tra kết nối."""
        # sourceOnDemand=False buộc MediaMTX kết nối trước khi có reader.
        self._request(
            f"/config/paths/add/{quote(path_name, safe='')}",
            method="POST",
            payload={
                "source": source,
                "sourceProtocol": "tcp",
                "sourceOnDemand": False,
            },
        )

    # ─────────────────────────────────────────────────────────────────────────

    def get_path(self, path_name: str) -> dict[str, object] | None:
        """Trả trạng thái runtime của path hoặc None khi path chưa xuất hiện."""
        try:
            return self._request(f"/paths/get/{quote(path_name, safe='')}")
        except MediaMtxError as exc:
            # Path có thể trả 404 trong lúc MediaMTX đang bắt đầu kết nối.
            if exc.status_code == 404:
                return None
            raise

    # ─────────────────────────────────────────────────────────────────────────

    def delete_path(self, path_name: str, ignore_missing: bool = True) -> None:
        """Xóa path cấu hình và tùy chọn bỏ qua trường hợp chưa tồn tại."""
        try:
            self._request(
                f"/config/paths/delete/{quote(path_name, safe='')}",
                method="DELETE",
            )
        except MediaMtxError as exc:
            if not ignore_missing or exc.status_code != 404:
                raise

    # ─────────────────────────────────────────────────────────────────────────

    def _request(
        self,
        path: str,
        method: str = "GET",
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Gửi JSON request và chuyển lỗi mạng thành lỗi miền nghiệp vụ."""
        # Không đưa payload/source vào thông báo lỗi để tránh lộ credentials.
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.api_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_text = response.read().decode("utf-8")
        except HTTPError as exc:
            raise MediaMtxError(
                f"MediaMTX trả HTTP {exc.code}.",
                status_code=exc.code,
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise MediaMtxError("Không kết nối được MediaMTX API.") from exc

        if not response_text:
            return {}
        try:
            decoded = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise MediaMtxError("MediaMTX trả JSON không hợp lệ.") from exc
        if not isinstance(decoded, dict):
            raise MediaMtxError("MediaMTX trả payload không đúng định dạng.")
        return decoded
