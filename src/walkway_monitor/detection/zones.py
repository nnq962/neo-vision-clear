"""Chuyển mask thay đổi thành polygon gọn nhẹ cho giao diện realtime."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class DifferenceZone:
    """Một vùng sai khác biểu diễn bằng polygon chuẩn hóa theo kích thước frame."""

    polygon: tuple[tuple[float, float], ...]
    area_ratio: float


# ─────────────────────────────────────────────────────────────────────────────


def extract_difference_zones(
    changed_mask: np.ndarray,
    maximum_zones: int = 20,
    maximum_vertices: int = 32,
) -> tuple[DifferenceZone, ...]:
    """Trích contour ngoài, đơn giản hóa và chuẩn hóa tọa độ về miền [0, 1]."""
    # Bước 1: xác thực giới hạn để payload luôn có kích thước bị chặn rõ ràng.
    mask = np.asarray(changed_mask)
    if mask.ndim != 2:
        raise ValueError("changed_mask phải là mảng hai chiều.")
    if maximum_zones < 1:
        raise ValueError("maximum_zones phải là số nguyên dương.")
    if maximum_vertices < 3:
        raise ValueError("maximum_vertices phải ít nhất là 3.")
    height, width = mask.shape
    if height == 0 or width == 0:
        return ()

    # Bước 2: chỉ lấy contour ngoài và ưu tiên vùng có diện tích lớn trước.
    binary_mask = (mask > 0).astype(np.uint8) * 255
    contours, _hierarchy = cv2.findContours(
        binary_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    # Bước 3: giảm số đỉnh rồi đổi pixel sang tỷ lệ để frontend resize tự do.
    zones: list[DifferenceZone] = []
    frame_area = float(width * height)
    x_denominator = float(max(width - 1, 1))
    y_denominator = float(max(height - 1, 1))
    for contour in contours[:maximum_zones]:
        area = float(cv2.contourArea(contour))
        if area <= 0:
            continue
        simplified = _simplify_contour(contour, maximum_vertices)
        if len(simplified) < 3:
            continue
        polygon = tuple(
            (
                float(np.clip(point[0] / x_denominator, 0.0, 1.0)),
                float(np.clip(point[1] / y_denominator, 0.0, 1.0)),
            )
            for point in simplified
        )
        zones.append(
            DifferenceZone(
                polygon=polygon,
                area_ratio=area / frame_area,
            )
        )
    return tuple(zones)


# ─────────────────────────────────────────────────────────────────────────────


def _simplify_contour(
    contour: np.ndarray,
    maximum_vertices: int,
) -> np.ndarray:
    """Tăng epsilon dần và lấy mẫu cuối cùng nếu contour vẫn quá nhiều đỉnh."""
    # Bước 1: thử nhiều mức đơn giản hóa để giữ hình dạng tốt khi có thể.
    perimeter = float(cv2.arcLength(contour, True))
    simplified = contour.reshape(-1, 2)
    for ratio in (0.005, 0.01, 0.02, 0.04, 0.08):
        approximated = cv2.approxPolyDP(contour, ratio * perimeter, True)
        simplified = approximated.reshape(-1, 2)
        if len(simplified) <= maximum_vertices:
            return simplified

    # Bước 2: lấy mẫu đều theo thứ tự contour để bảo đảm hard limit payload.
    indices = np.linspace(
        0,
        len(simplified) - 1,
        maximum_vertices,
        dtype=np.int32,
    )
    return simplified[indices]
