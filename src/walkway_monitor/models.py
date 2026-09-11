"""Các kiểu dữ liệu dùng chung cho calibration và detection."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


BASELINE_FORMAT_VERSION = 1


@dataclass(frozen=True)
class WorldCoordinates:
    """Tọa độ thực tương ứng với từng đỉnh ROI và mô tả hệ quy chiếu."""

    points: np.ndarray
    unit: str
    origin: str
    x_axis: str
    y_axis: str

    # ─────────────────────────────────────────────────────────────────────────

    def validate(self, expected_point_count: int) -> None:
        """Kiểm tra số điểm, giá trị tọa độ và mô tả hệ quy chiếu."""
        points = np.asarray(self.points)
        if points.shape != (expected_point_count, 2):
            raise ValueError(
                "Tọa độ thực phải có shape "
                f"({expected_point_count}, 2), nhận được {points.shape}."
            )
        if not np.all(np.isfinite(points)):
            raise ValueError("Tọa độ thực chứa giá trị không hữu hạn.")
        descriptions = (self.unit, self.origin, self.x_axis, self.y_axis)
        if any(
            not isinstance(value, str) or not value.strip()
            for value in descriptions
        ):
            raise ValueError("Thông tin hệ tọa độ thực không được để trống.")


# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RoiDefinition:
    """Polygon ROI được lưu bằng tọa độ chuẩn hóa trong khoảng từ 0 đến 1."""

    normalized_points: np.ndarray
    world_coordinates: WorldCoordinates | None = None

    # ─────────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Kiểm tra polygon có hình dạng và miền tọa độ hợp lệ."""
        points = np.asarray(self.normalized_points)
        if points.ndim != 2 or points.shape[1:] != (2,) or len(points) < 3:
            raise ValueError("ROI phải là mảng (N, 2) và có ít nhất 3 điểm.")
        if not np.all(np.isfinite(points)):
            raise ValueError("ROI chứa tọa độ không hữu hạn.")
        if np.any(points < 0.0) or np.any(points > 1.0):
            raise ValueError("Tọa độ chuẩn hóa của ROI phải nằm trong [0, 1].")
        if self.world_coordinates is not None:
            self.world_coordinates.validate(len(points))

    # ─────────────────────────────────────────────────────────────────────────

    def to_pixel_points(self, width: int, height: int) -> np.ndarray:
        """Chuyển polygon chuẩn hóa thành tọa độ pixel ở độ phân giải yêu cầu."""
        self.validate()
        if width <= 0 or height <= 0:
            raise ValueError("Kích thước frame phải là số dương.")
        scale = np.array([width - 1, height - 1], dtype=np.float32)
        points = np.rint(self.normalized_points.astype(np.float32) * scale)
        points[:, 0] = np.clip(points[:, 0], 0, width - 1)
        points[:, 1] = np.clip(points[:, 1], 0, height - 1)
        return points.astype(np.int32)

    # ─────────────────────────────────────────────────────────────────────────

    def to_mask(self, width: int, height: int) -> np.ndarray:
        """Tạo mask uint8 có giá trị 255 bên trong polygon ROI."""
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(mask, [self.to_pixel_points(width, height)], 255)
        return mask


@dataclass(frozen=True)
class BaselineArtifact:
    """Dữ liệu baseline đã tổng hợp và sẵn sàng cho bước detection."""

    reference_depth: np.ndarray
    noise_map: np.ndarray
    roi: RoiDefinition
    frame_width: int
    frame_height: int
    encoder: str
    input_size: int
    frame_count: int
    created_at: str
    source_type: str
    alignment_median_error: float
    noise_p99: float
    format_version: int = BASELINE_FORMAT_VERSION

    # ─────────────────────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Kiểm tra artifact đầy đủ, hữu hạn và nhất quán về kích thước."""
        self.roi.validate()
        if self.frame_width <= 1 or self.frame_height <= 1:
            raise ValueError("Độ phân giải baseline không hợp lệ.")
        expected_shape = (self.frame_height, self.frame_width)
        if self.reference_depth.shape != expected_shape:
            raise ValueError("reference_depth không khớp độ phân giải baseline.")
        if self.noise_map.shape != expected_shape:
            raise ValueError("noise_map không khớp độ phân giải baseline.")
        if not np.all(np.isfinite(self.reference_depth)):
            raise ValueError("reference_depth chứa giá trị không hữu hạn.")
        if not np.all(np.isfinite(self.noise_map)) or np.any(self.noise_map < 0):
            raise ValueError("noise_map phải hữu hạn và không âm.")
        if self.frame_count < 5:
            raise ValueError("Baseline phải được tạo từ ít nhất 5 frame.")
        if self.format_version != BASELINE_FORMAT_VERSION:
            raise ValueError(
                f"Phiên bản baseline không hỗ trợ: {self.format_version}."
            )
