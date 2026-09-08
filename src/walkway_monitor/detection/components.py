"""Lọc mask và trích xuất connected component trong ROI."""

from __future__ import annotations

import cv2
import numpy as np

from walkway_monitor.detection.models import ComponentStats


def clean_changed_mask(
    changed_mask: np.ndarray,
    roi_mask: np.ndarray,
    kernel_size: int,
) -> np.ndarray:
    """Loại đốm nhiễu, nối vùng gần nhau và giới hạn kết quả trong ROI."""
    if changed_mask.shape != roi_mask.shape:
        raise ValueError("changed_mask và roi_mask phải cùng kích thước.")
    if changed_mask.ndim != 2:
        raise ValueError("Mask phải là mảng hai chiều.")
    kernel_size = max(3, int(kernel_size))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (kernel_size, kernel_size),
    )
    cleaned = cv2.morphologyEx(
        changed_mask.astype(np.uint8),
        cv2.MORPH_OPEN,
        kernel,
    )
    cleaned = cv2.morphologyEx(
        cleaned,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=2,
    )
    cleaned[roi_mask == 0] = 0
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────


def largest_component(mask: np.ndarray) -> ComponentStats:
    """Trả về diện tích và bounding box của component foreground lớn nhất."""
    if mask.ndim != 2:
        raise ValueError("Mask phải là mảng hai chiều.")
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8),
        connectivity=8,
    )
    if count <= 1:
        return ComponentStats(area=0, bounding_box=None)
    areas = stats[1:, cv2.CC_STAT_AREA]
    component_index = int(np.argmax(areas)) + 1
    x = int(stats[component_index, cv2.CC_STAT_LEFT])
    y = int(stats[component_index, cv2.CC_STAT_TOP])
    width = int(stats[component_index, cv2.CC_STAT_WIDTH])
    height = int(stats[component_index, cv2.CC_STAT_HEIGHT])
    return ComponentStats(
        area=int(stats[component_index, cv2.CC_STAT_AREA]),
        bounding_box=(x, y, width, height),
    )


# ─────────────────────────────────────────────────────────────────────────────


def filter_components_by_area(mask: np.ndarray, minimum_area: int) -> np.ndarray:
    """Chỉ giữ các connected component có diện tích không nhỏ hơn ngưỡng."""
    if mask.ndim != 2:
        raise ValueError("Mask phải là mảng hai chiều.")
    if minimum_area <= 1:
        return mask.astype(np.uint8, copy=True)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8),
        connectivity=8,
    )
    filtered = np.zeros_like(mask, dtype=np.uint8)
    for component_index in range(1, count):
        area = int(stats[component_index, cv2.CC_STAT_AREA])
        if area >= minimum_area:
            filtered[labels == component_index] = 255
    return filtered
