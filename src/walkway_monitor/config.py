"""Cấu hình cho các pipeline của walkway monitor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationConfig:
    """Cấu hình quá trình thu và tổng hợp baseline của lối đi trống."""

    frame_count: int = 60
    input_size: int = 518
    process_width: int = 960
    encoder: str = "vits"

    # ─────────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Kiểm tra các giá trị cấu hình trước khi mở nguồn media."""
        if self.frame_count < 5:
            raise ValueError("frame_count phải lớn hơn hoặc bằng 5.")
        if self.input_size < 14:
            raise ValueError("input_size phải lớn hơn hoặc bằng 14.")
        if self.process_width < 0:
            raise ValueError("process_width không được âm.")
        if self.encoder not in {"vits", "vitb", "vitl"}:
            raise ValueError(f"Encoder không được hỗ trợ: {self.encoder}")


@dataclass(frozen=True)
class DetectionConfig:
    """Cấu hình tạo mask thay đổi và ổn định trạng thái detection."""

    noise_multiplier: float = 6.0
    minimum_difference: float = 0.03
    minimum_area_ratio: float = 0.01
    occupied_frames: int = 5
    clear_frames: int = 8
    camera_difference_threshold: float = 0.12
    camera_change_area_ratio: float = 0.25
    morphology_divisor: int = 180
    depth_blur_kernel: int = 5
    roi_border_margin: int = 6
    mask_temporal_window: int = 5
    mask_temporal_required: int = 3
    display_minimum_area_ratio: float = 0.001

    # ─────────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Kiểm tra các threshold và số frame xác nhận của detector."""
        if self.noise_multiplier < 0:
            raise ValueError("noise_multiplier không được âm.")
        if self.minimum_difference <= 0:
            raise ValueError("minimum_difference phải là số dương.")
        if not 0 < self.minimum_area_ratio < 1:
            raise ValueError("minimum_area_ratio phải nằm trong (0, 1).")
        if self.occupied_frames < 1 or self.clear_frames < 1:
            raise ValueError("Số frame xác nhận phải lớn hơn hoặc bằng 1.")
        if self.camera_difference_threshold <= 0:
            raise ValueError("camera_difference_threshold phải là số dương.")
        if not 0 < self.camera_change_area_ratio <= 1:
            raise ValueError("camera_change_area_ratio phải nằm trong (0, 1].")
        if self.morphology_divisor < 1:
            raise ValueError("morphology_divisor phải lớn hơn hoặc bằng 1.")
        if self.depth_blur_kernel < 1 or self.depth_blur_kernel % 2 == 0:
            raise ValueError("depth_blur_kernel phải là số lẻ dương.")
        if self.roi_border_margin < 0:
            raise ValueError("roi_border_margin không được âm.")
        if self.mask_temporal_window < 1:
            raise ValueError("mask_temporal_window phải lớn hơn hoặc bằng 1.")
        if not 1 <= self.mask_temporal_required <= self.mask_temporal_window:
            raise ValueError(
                "mask_temporal_required phải nằm trong [1, mask_temporal_window]."
            )
        if not 0 <= self.display_minimum_area_ratio < 1:
            raise ValueError("display_minimum_area_ratio phải nằm trong [0, 1).")
