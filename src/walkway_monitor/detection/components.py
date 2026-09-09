"""Lọc mask và trích xuất connected component trong ROI."""

from __future__ import annotations

import cv2
import numpy as np

from walkway_monitor.detection.models import ComponentStats, WalkwayClearanceStats


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


# ─────────────────────────────────────────────────────────────────────────────


def measure_walkway_clearance(
    obstacle_mask: np.ndarray,
    roi_mask: np.ndarray,
    smoothing_rows: int,
) -> WalkwayClearanceStats:
    """Đo khoảng trống liên tục lớn nhất trên từng lát cắt ngang của ROI."""
    if obstacle_mask.shape != roi_mask.shape:
        raise ValueError("obstacle_mask và roi_mask phải cùng kích thước.")
    if obstacle_mask.ndim != 2:
        raise ValueError("Mask phải là mảng hai chiều.")
    if smoothing_rows < 1 or smoothing_rows % 2 == 0:
        raise ValueError("smoothing_rows phải là số lẻ dương.")

    roi = roi_mask > 0
    obstacle = (obstacle_mask > 0) & roi
    rows: list[int] = []
    spans: list[tuple[int, int]] = []
    free_width_ratios: list[float] = []
    obstacle_width_ratios: list[float] = []

    for row in range(roi.shape[0]):
        columns = np.flatnonzero(roi[row])
        if columns.size < 2:
            continue
        left, right = int(columns[0]), int(columns[-1])
        row_roi = roi[row, left : right + 1]
        row_obstacle = obstacle[row, left : right + 1]
        free = row_roi & ~row_obstacle
        padded = np.pad(free.astype(np.int8), (1, 1))
        transitions = np.diff(padded)
        starts = np.flatnonzero(transitions == 1)
        ends = np.flatnonzero(transitions == -1)
        largest_free_width = int(np.max(ends - starts)) if starts.size else 0
        roi_width = int(np.count_nonzero(row_roi))

        rows.append(row)
        spans.append((left, right))
        free_width_ratios.append(largest_free_width / roi_width)
        obstacle_width_ratios.append(
            float(np.count_nonzero(row_obstacle) / roi_width)
        )

    if not rows:
        return WalkwayClearanceStats(1.0, 0.0, None, None)

    free_profile = np.asarray(free_width_ratios, dtype=np.float32)
    obstacle_profile = np.asarray(obstacle_width_ratios, dtype=np.float32)
    half_window = smoothing_rows // 2
    smoothed_profile = np.empty_like(free_profile)
    smoothed_obstacle_profile = np.empty_like(obstacle_profile)
    for index in range(free_profile.size):
        start = max(0, index - half_window)
        end = min(free_profile.size, index + half_window + 1)
        smoothed_profile[index] = np.median(free_profile[start:end])
        smoothed_obstacle_profile[index] = np.median(
            obstacle_profile[start:end]
        )

    bottleneck_index = int(np.argmin(smoothed_profile))
    return WalkwayClearanceStats(
        minimum_free_width_ratio=float(smoothed_profile[bottleneck_index]),
        obstacle_width_ratio=float(smoothed_obstacle_profile[bottleneck_index]),
        bottleneck_row=rows[bottleneck_index],
        bottleneck_span=spans[bottleneck_index],
    )
