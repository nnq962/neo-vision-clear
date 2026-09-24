"""Schema tài liệu cấu hình duy nhất của backend."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.models.calibration import CalibrationConfig
from server.models.camera import CameraConfig
from server.models.uart import UartConfig
from walkway_monitor.config import DetectionConfig


class RuntimeDetectionConfig(BaseModel):
    """Các tham số biến đổi depth thành phép đo hành lang khi chạy runtime."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    noise_multiplier: float = Field(default=6.0, ge=0)
    minimum_difference: float = Field(default=0.03, gt=0)
    bev_pixels_per_meter: float = Field(default=100.0, gt=0)
    morphology_divisor: int = Field(default=180, ge=1)
    depth_blur_kernel: int = Field(default=5, ge=1)
    check_area_padding: int = Field(default=12, ge=0)
    depth_alignment: bool = True
    alignment_inlier_ratio: float = Field(default=0.55, gt=0.5, le=1)
    display_minimum_area_ratio: float = Field(default=0.001, ge=0, lt=1)

    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_blur_kernel(self) -> "RuntimeDetectionConfig":
        """Bảo đảm Gaussian blur sử dụng kích thước kernel lẻ."""
        # OpenCV yêu cầu mỗi chiều kernel Gaussian là số lẻ dương.
        if self.depth_blur_kernel % 2 == 0:
            raise ValueError("depth_blur_kernel phải là số lẻ dương.")
        return self

    # ─────────────────────────────────────────────────────────────────────────

    def to_detection_config(self) -> DetectionConfig:
        """Chuyển schema JSON thành cấu hình miền của detection pipeline."""
        # Bước 1: tên field được giữ đồng nhất để không cần ánh xạ thủ công.
        return DetectionConfig(**self.model_dump())


class RuntimeConfig(BaseModel):
    """Cấu hình đầy đủ để chọn các baseline và chạy worker detection."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    enabled: bool = False
    active_baseline_ids: list[str] = Field(default_factory=list, max_length=32)
    snapshot_max_age_seconds: float = Field(default=2.0, gt=0)
    log_interval_seconds: float = Field(default=2.0, ge=0)
    detection: RuntimeDetectionConfig = Field(default_factory=RuntimeDetectionConfig)

    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_active_baseline(self) -> "RuntimeConfig":
        """Yêu cầu danh sách baseline không trùng và hợp lệ khi bật runtime."""
        # Bước 1: không cho cùng một baseline xuất hiện hai lần trong batch.
        if len(set(self.active_baseline_ids)) != len(self.active_baseline_ids):
            raise ValueError("active_baseline_ids không được chứa giá trị trùng.")

        # Bước 2: runtime tắt được phép chưa chọn baseline để cấu hình ban đầu.
        if self.enabled and not self.active_baseline_ids:
            raise ValueError("Runtime đang bật phải có active_baseline_ids.")

        return self


class RuntimeProcessResponse(BaseModel):
    """Trạng thái thực tế của worker runtime độc lập với cấu hình đã lưu."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["stopped", "starting", "running", "stopping", "failed"]
    active_baseline_ids: list[str] = Field(default_factory=list)
    snapshot_age_ms: int | None = None
    error: str | None = None
    started_at: datetime | None = None


class AppConfigDocument(BaseModel):
    """Tài liệu data/config.json chứa camera, baseline, runtime và UART."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    cameras: list[CameraConfig] = Field(default_factory=list)
    baselines: list[CalibrationConfig] = Field(default_factory=list)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    uart: UartConfig = Field(default_factory=UartConfig)

    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_runtime_relationships(self) -> "AppConfigDocument":
        """Kiểm tra các baseline runtime tồn tại và thuộc camera khác nhau."""
        # Bước 1: runtime chưa chọn baseline không tạo thêm ràng buộc quan hệ.
        baseline_ids = self.runtime.active_baseline_ids
        if not baseline_ids:
            return self

        # Bước 2: resolve đủ baseline và camera theo đúng thứ tự batch đã chọn.
        selected_baselines = []
        for baseline_id in baseline_ids:
            baseline = next(
                (item for item in self.baselines if item.id == baseline_id),
                None,
            )
            if baseline is None:
                raise ValueError(f"Không tìm thấy active baseline '{baseline_id}'.")
            if not any(camera.id == baseline.camera_id for camera in self.cameras):
                raise ValueError("Active baseline không thuộc camera hiện có.")
            selected_baselines.append(baseline)

        # Bước 3: mỗi camera chỉ góp một frame vào một lượt inference.
        camera_ids = [baseline.camera_id for baseline in selected_baselines]
        if len(set(camera_ids)) != len(camera_ids):
            raise ValueError("Mỗi camera chỉ được chọn một baseline cho runtime.")

        # Bước 4: các baseline dùng chung model phải cùng encoder và input size.
        model_specs = {
            (baseline.encoder, baseline.input_size, baseline.process_width)
            for baseline in selected_baselines
        }
        if len(model_specs) > 1:
            raise ValueError(
                "Các baseline trong cùng batch phải dùng cùng encoder, "
                "input_size và process_width."
            )
        return self
