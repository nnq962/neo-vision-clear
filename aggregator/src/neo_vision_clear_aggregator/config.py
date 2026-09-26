"""Đọc và xác thực cấu hình nghiệp vụ của Aggregator."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class CorridorConfig(BaseModel):
    """Thông tin hành lang và kích thước tối thiểu robot cần."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    corridor_id: str = Field(min_length=1, max_length=100)
    corridor_name: str = Field(min_length=1, max_length=200)
    required_width_cm: float = Field(gt=0)


class CameraLocationConfig(BaseModel):
    """Ánh xạ một camera edge vào vị trí cố định trong hành lang."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    camera_id: str = Field(min_length=1, max_length=100)
    source_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
    )
    order: int = Field(ge=1)
    location_name: str = Field(min_length=1, max_length=200)


class OutboundConfig(BaseModel):
    """Cấu hình kết nối một chiều từ Aggregator tới WS server đích."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool = False
    websocket_url: Optional[str] = None
    reconnect_seconds: float = Field(default=2.0, gt=0)

    @model_validator(mode="after")
    def validate_websocket_url(self) -> "OutboundConfig":
        """Yêu cầu URL WS hợp lệ khi outbound được bật."""
        # Bước 1: chế độ tắt cho phép để trống URL trong môi trường phát triển.
        if not self.enabled:
            return self
        if not self.websocket_url or not self.websocket_url.startswith(
            ("ws://", "wss://")
        ):
            raise ValueError(
                "outbound.websocket_url phải bắt đầu bằng ws:// hoặc wss://."
            )
        return self


class AggregatorConfig(BaseModel):
    """Toàn bộ cấu hình nghiệp vụ được nạp một lần khi process khởi động."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    corridor: CorridorConfig
    cameras: List[CameraLocationConfig] = Field(min_length=1)
    outbound: OutboundConfig = Field(default_factory=OutboundConfig)

    @model_validator(mode="after")
    def validate_camera_mappings(self) -> "AggregatorConfig":
        """Không cho camera ID hoặc thứ tự vị trí bị trùng."""
        # Bước 1: camera_id là khóa join giữa Jetson và Aggregator.
        camera_ids = [camera.camera_id for camera in self.cameras]
        if len(camera_ids) != len(set(camera_ids)):
            raise ValueError("cameras không được trùng camera_id.")

        # Bước 2: order phải duy nhất để server xác định đúng trình tự hành lang.
        orders = [camera.order for camera in self.cameras]
        if len(orders) != len(set(orders)):
            raise ValueError("cameras không được trùng order.")
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("cameras.order phải liên tiếp từ 1 đến số camera.")
        return self

    def camera_map(self) -> dict[str, CameraLocationConfig]:
        """Trả ánh xạ camera ID để registry tra cứu theo O(1)."""
        return {camera.camera_id: camera for camera in self.cameras}


class AggregatorConfigError(RuntimeError):
    """Báo lỗi tệp cấu hình không tồn tại hoặc không đúng schema."""


def load_config(path: str) -> AggregatorConfig:
    """Đọc JSON tại đường dẫn cấu hình và chuẩn hóa lỗi startup."""
    config_path = Path(path)
    try:
        # Bước 1: dùng UTF-8 để tên hành lang và vị trí hỗ trợ tiếng Việt.
        with config_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        return AggregatorConfig.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise AggregatorConfigError(
            f"Không thể đọc cấu hình Aggregator tại '{config_path}': {exc}"
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────


def save_config(path: str, config: AggregatorConfig) -> None:
    """Ghi cấu hình nguyên tử để mất điện không tạo JSON dở dang."""
    config_path = Path(path)
    temporary_path = None
    try:
        # Bước 1: tạo file tạm cùng thư mục để os.replace luôn cùng filesystem.
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(config_path.parent),
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(
                config.model_dump(mode="json"),
                stream,
                ensure_ascii=False,
                indent=2,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        # Bước 2: thay file đích chỉ sau khi nội dung mới đã ghi hoàn chỉnh.
        os.replace(temporary_path, config_path)
    except OSError as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise AggregatorConfigError(
            f"Không thể lưu cấu hình Aggregator tại '{config_path}': {exc}"
        ) from exc
