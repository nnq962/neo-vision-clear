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
    """Cấu hình so sánh depth và tạo mask thay đổi cho từng frame."""

    noise_multiplier           : float = 6.0
    minimum_difference         : float = 0.03
    bev_pixels_per_meter       : float = 100.0
    morphology_divisor         : int   = 180
    depth_blur_kernel          : int   = 5
    check_area_padding         : int   = 12
    depth_alignment            : bool  = True
    alignment_inlier_ratio     : float = 0.55
    display_minimum_area_ratio : float = 0.001

    # ─────────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Kiểm tra các threshold và tham số xử lý mask của detector."""
        if self.noise_multiplier < 0:
            raise ValueError("noise_multiplier không được âm.")
        if self.minimum_difference <= 0:
            raise ValueError("minimum_difference phải là số dương.")
        if self.bev_pixels_per_meter <= 0:
            raise ValueError("bev_pixels_per_meter phải là số dương.")
        if self.morphology_divisor < 1:
            raise ValueError("morphology_divisor phải lớn hơn hoặc bằng 1.")
        if self.depth_blur_kernel < 1 or self.depth_blur_kernel % 2 == 0:
            raise ValueError("depth_blur_kernel phải là số lẻ dương.")
        if self.check_area_padding < 0:
            raise ValueError("check_area_padding không được âm.")
        if not 0.5 < self.alignment_inlier_ratio <= 1:
            raise ValueError("alignment_inlier_ratio phải nằm trong (0.5, 1].")
        if not 0 <= self.display_minimum_area_ratio < 1:
            raise ValueError("display_minimum_area_ratio phải nằm trong [0, 1).")
