"""Schema cấu hình camera dùng cho JSON store và REST API."""

from __future__ import annotations

from datetime import datetime
from typing_extensions import Annotated
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────


def validate_camera_source(source: str) -> str:
    """Xác nhận source là một URL RTSP hoặc RTMP hoàn chỉnh."""
    # Credentials được phép nằm trực tiếp trong URL để form chỉ có một ô.
    parsed = urlsplit(source)
    valid_schemes = {"rtsp", "rtsps", "rtmp", "rtmps"}
    if parsed.scheme not in valid_schemes or not parsed.hostname:
        raise ValueError("Camera cần URL RTSP hoặc RTMP hợp lệ.")
    return source


CameraSource = Annotated[
    str,
    Field(min_length=1, max_length=2048),
    AfterValidator(validate_camera_source),
]


class CameraFields(BaseModel):
    """Các trường cấu hình camera tối thiểu của MVP."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    source: CameraSource
    open_timeout_ms: int = Field(default=5000, ge=0, le=120_000)
    read_timeout_ms: int = Field(default=5000, ge=0, le=120_000)


class CameraCreate(CameraFields):
    """Payload tạo mới một camera."""


class CameraUpdate(BaseModel):
    """Payload cập nhật từng phần tên hoặc URL camera."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    source: CameraSource | None = None
    open_timeout_ms: int | None = Field(default=None, ge=0, le=120_000)
    read_timeout_ms: int | None = Field(default=None, ge=0, le=120_000)

    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_patch(self) -> "CameraUpdate":
        """Từ chối payload rỗng hoặc giá trị null."""
        if not self.model_fields_set:
            raise ValueError("Payload cập nhật phải có ít nhất một trường.")
        invalid_fields = [
            field_name
            for field_name in self.model_fields_set
            if getattr(self, field_name) is None
        ]
        if invalid_fields:
            joined_fields = ", ".join(sorted(invalid_fields))
            raise ValueError(f"Các trường không được null: {joined_fields}.")
        return self


class CameraConfig(CameraFields):
    """Bản ghi camera đầy đủ được lưu nội bộ trong tệp JSON."""

    id: str
    created_at: datetime
    updated_at: datetime

    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_fields(cls, value: object) -> object:
        """Đọc bản ghi cũ và gộp credentials trở lại URL source."""
        if not isinstance(value, dict):
            return value

        # Bản sao tránh sửa object mà JSON loader hoặc caller đang sở hữu.
        payload = dict(value)
        username = payload.pop("username", None)
        password = payload.pop("password", None)
        for field_name in (
            "source_type",
            "enabled",
            "use_gstreamer",
        ):
            payload.pop(field_name, None)

        source = payload.get("source")
        if username and isinstance(source, str):
            parsed = urlsplit(source)
            encoded_password = (
                f":{quote(str(password), safe='')}" if password else ""
            )
            payload["source"] = urlunsplit(
                (
                    parsed.scheme,
                    f"{quote(str(username), safe='')}{encoded_password}@{parsed.netloc}",
                    parsed.path,
                    parsed.query,
                    parsed.fragment,
                )
            )
        return payload

    # ─────────────────────────────────────────────────────────────────────────

    def to_response(self) -> "CameraResponse":
        """Chuyển bản ghi lưu trữ thành response API."""
        # Schema lưu và trả về giống nhau để giữ luồng MVP đơn giản.
        return CameraResponse.model_validate(self.model_dump())


class CameraResponse(CameraConfig):
    """Thông tin camera được trả về client."""
