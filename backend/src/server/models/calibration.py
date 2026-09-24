"""Schema cấu hình calibration dùng cho JSON store và REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


Point = Tuple[float, float]


class CalibrationFields(BaseModel):
    """Các tham số cần lưu trước khi chạy calibration."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1, max_length=100)
    roi_points: list[Point] = Field(min_length=4, max_length=4)
    world_points: list[Point] = Field(min_length=4, max_length=4)
    unit: Literal["m"] = "m"
    origin: str = Field(default="P1", min_length=1, max_length=100)
    x_axis: str = Field(default="P1 → P2", min_length=1, max_length=100)
    y_axis: str = Field(default="P1 → P4", min_length=1, max_length=100)
    encoder: Literal["vits", "vitb", "vitl"] = "vits"
    frame_count: int = Field(default=60, ge=5, le=10_000)
    input_size: int = Field(default=518, ge=14, le=4096)
    process_width: int = Field(default=960, ge=0, le=16_384)

    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_points(self) -> "CalibrationFields":
        """Kiểm tra bốn điểm ROI và tọa độ thực tạo thành vùng hợp lệ."""
        # Bước 1: tọa độ ROI gửi từ giao diện phải được chuẩn hóa theo video.
        if any(
            coordinate < 0.0 or coordinate > 1.0
            for point in self.roi_points
            for coordinate in point
        ):
            raise ValueError("Tọa độ ROI phải nằm trong khoảng [0, 1].")

        # Bước 2: từ chối điểm trùng và polygon suy biến trước khi lưu.
        if len(set(self.roi_points)) != 4:
            raise ValueError("Bốn điểm ROI không được trùng nhau.")
        if len(set(self.world_points)) != 4:
            raise ValueError("Bốn tọa độ thực không được trùng nhau.")
        if abs(_polygon_signed_area(self.roi_points)) <= 1e-8:
            raise ValueError("Bốn điểm ROI không tạo thành một vùng hợp lệ.")
        if abs(_polygon_signed_area(self.world_points)) <= 1e-8:
            raise ValueError("Bốn tọa độ thực không tạo thành một vùng hợp lệ.")
        return self


class CalibrationCreate(CalibrationFields):
    """Payload tạo một cấu hình baseline mới."""


class CalibrationCreateRequest(CalibrationFields):
    """Payload API tạo baseline và chỉ định camera sở hữu."""

    camera_id: str = Field(min_length=1, max_length=100)


class CalibrationUpdate(CalibrationFields):
    """Payload thay thế toàn bộ cấu hình của một baseline."""


class CalibrationConfig(CalibrationFields):
    """Bản ghi calibration đầy đủ được lưu ở backend."""

    id: str
    camera_id: str
    created_at: datetime
    updated_at: datetime

    # ─────────────────────────────────────────────────────────────────────────

    def to_response(self) -> "CalibrationResponse":
        """Chuyển bản ghi lưu trữ thành response API."""
        return CalibrationResponse.model_validate(self.model_dump())


class CalibrationResponse(CalibrationConfig):
    """Cấu hình calibration được trả về frontend."""


class CalibrationRunResponse(BaseModel):
    """Trạng thái một công việc tạo artifact baseline."""

    model_config = ConfigDict(extra="forbid")

    baseline_id: str
    status: Literal["idle", "running", "completed", "failed"]
    processed_frames: int = 0
    total_frames: int
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact_available: bool = False
    noise_p99: float | None = None
    alignment_median_error: float | None = None


# ─────────────────────────────────────────────────────────────────────────────


def _polygon_signed_area(points: list[Point]) -> float:
    """Tính diện tích có dấu của polygon theo công thức shoelace."""
    # Bước 1: ghép mỗi đỉnh với đỉnh kế tiếp, kể cả cạnh đóng polygon.
    area_twice = 0.0
    for index, (x_value, y_value) in enumerate(points):
        next_x, next_y = points[(index + 1) % len(points)]
        area_twice += x_value * next_y - next_x * y_value

    # Bước 2: chia đôi tổng tích chéo để thu được diện tích có dấu.
    return area_twice / 2.0
