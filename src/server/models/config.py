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
    """Cấu hình đầy đủ để chọn baseline và chạy worker detection."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    enabled: bool = False
    active_baseline_id: str | None = None
    snapshot_max_age_seconds: float = Field(default=2.0, gt=0)
    log_interval_seconds: float = Field(default=2.0, ge=0)
    detection: RuntimeDetectionConfig = Field(default_factory=RuntimeDetectionConfig)

    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_active_baseline(self) -> "RuntimeConfig":
        """Yêu cầu chọn baseline trước khi bật runtime."""
        # Runtime tắt được phép chưa chọn baseline để hỗ trợ cấu hình ban đầu.
        if self.enabled and self.active_baseline_id is None:
            raise ValueError("Runtime đang bật phải có active_baseline_id.")
        return self


class RuntimeProcessResponse(BaseModel):
    """Trạng thái thực tế của worker runtime độc lập với cấu hình đã lưu."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["stopped", "starting", "running", "stopping", "failed"]
    active_baseline_id: str | None = None
    snapshot_age_ms: int | None = None
    error: str | None = None
    started_at: datetime | None = None


class AppConfigDocument(BaseModel):
    """Tài liệu data/config.json chứa camera, baseline, runtime và UART."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    camera: CameraConfig | None = None
    baselines: list[CalibrationConfig] = Field(default_factory=list)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    uart: UartConfig = Field(default_factory=UartConfig)

    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_runtime_relationships(self) -> "AppConfigDocument":
        """Kiểm tra baseline runtime tồn tại và thuộc camera hiện tại."""
        # Bước 1: runtime chưa chọn baseline không tạo thêm ràng buộc quan hệ.
        baseline_id = self.runtime.active_baseline_id
        if baseline_id is None:
            return self

        # Bước 2: ID active phải tham chiếu đúng một baseline đã lưu.
        baseline = next(
            (item for item in self.baselines if item.id == baseline_id),
            None,
        )
        if baseline is None:
            raise ValueError(
                f"Không tìm thấy active baseline '{baseline_id}'."
            )

        # Bước 3: baseline active phải thuộc camera singleton hiện tại.
        if self.camera is None or baseline.camera_id != self.camera.id:
            raise ValueError("Active baseline không thuộc camera hiện tại.")
        return self

    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_document(cls, value: object) -> object:
        """Chuẩn hóa các tài liệu camera hoặc calibration cũ về schema chung."""
        if not isinstance(value, dict):
            return value

        # Bước 1: lấy camera singleton hoặc camera mới nhất từ schema danh sách cũ.
        payload = dict(value)
        camera = payload.get("camera")
        cameras = payload.get("cameras")
        if camera is None and isinstance(cameras, list) and cameras:
            camera = cameras[-1]

        # Bước 2: chuyển calibration singleton cũ thành một baseline có danh tính.
        baselines = payload.get("baselines", [])
        if not isinstance(baselines, list):
            baselines = []
        calibration = payload.get("calibration")
        if isinstance(calibration, dict):
            migrated = dict(calibration)
            migrated.setdefault("id", "legacy-baseline")
            migrated.setdefault("name", "Baseline đã lưu")
            baselines = [*baselines, migrated]

        # Bước 3: chỉ trả các trường thuộc schema mới để loại metadata legacy.
        return {
            "version": 2,
            "camera": camera,
            "baselines": baselines,
            "runtime": payload.get("runtime", RuntimeConfig()),
            "uart": payload.get("uart", UartConfig()),
        }
