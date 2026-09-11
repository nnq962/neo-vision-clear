"""Làm sạch mask và đo khả năng đi xuyên suốt trên raster BEV."""

from __future__ import annotations

import cv2
import numpy as np

from walkway_monitor.detection.models import RouteCapacity


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

    # Bước 1: chuẩn hóa kernel thành số lẻ để morphology có tâm xác định.
    kernel_size = max(3, int(kernel_size))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (kernel_size, kernel_size),
    )

    # Bước 2: bỏ đốm nhỏ, nối vùng gần nhau rồi cắt kết quả về vùng kiểm tra.
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


def filter_components_by_area(mask: np.ndarray, minimum_area: int) -> np.ndarray:
    """Chỉ giữ các connected component có diện tích không nhỏ hơn ngưỡng."""
    if mask.ndim != 2:
        raise ValueError("Mask phải là mảng hai chiều.")
    if minimum_area <= 1:
        return mask.astype(np.uint8, copy=True)

    # Bước 1: gắn nhãn mọi vùng thay đổi độc lập trong mask.
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8),
        connectivity=8,
    )

    # Bước 2: chỉ sao chép các vùng đủ lớn sang mask kết quả.
    filtered = np.zeros_like(mask, dtype=np.uint8)
    for component_index in range(1, count):
        area = int(stats[component_index, cv2.CC_STAT_AREA])
        if area >= minimum_area:
            filtered[labels == component_index] = 255
    return filtered


# ─────────────────────────────────────────────────────────────────────────────


def measure_route_capacity(
    obstacle_mask: np.ndarray,
    roi_mask: np.ndarray,
    entrance_mask: np.ndarray,
    exit_mask: np.ndarray,
    pixels_per_meter: float,
    minimum_world_x: float,
    minimum_world_y: float,
) -> RouteCapacity:
    """Tìm bề rộng lớn nhất có vùng tâm nối từ đầu đến cuối hành lang."""
    masks = (obstacle_mask, roi_mask, entrance_mask, exit_mask)
    if any(mask.shape != roi_mask.shape or mask.ndim != 2 for mask in masks):
        raise ValueError("Các mask BEV phải là mảng 2D cùng kích thước.")
    if pixels_per_meter <= 0:
        raise ValueError("pixels_per_meter phải là số dương.")

    # Bước 1: tạo free-space và xác định hai mép vào/ra theo trục Y thực.
    roi = roi_mask > 0
    free = roi & ~(obstacle_mask > 0)
    valid_rows = np.flatnonzero(np.any(roi, axis=1))
    if valid_rows.size < 2:
        raise ValueError("ROI trên raster BEV không có chiều dài hợp lệ.")
    entrance = (entrance_mask > 0) & roi
    exit_area = (exit_mask > 0) & roi
    if not np.any(entrance) or not np.any(exit_area):
        raise ValueError("Hai cạnh vào/ra của ROI BEV không hợp lệ.")

    # Hai cạnh vào/ra là cổng mở chứ không phải tường. Với cổng nghiêng, phần
    # footprint còn nằm ngoài ROI trong lúc đi qua vẫn phải được xem là trống.
    traversal_free = free.copy()
    opening_rows = np.any(entrance | exit_area, axis=1)
    obstacle = obstacle_mask > 0
    traversal_free[opening_rows] = ~obstacle[opening_rows]

    # Bước 2: tìm nhị phân bề rộng footprint có thể trượt theo X và vẫn tạo
    # thành một connected component nối mép vào với mép ra.
    maximum_candidate = int(np.max(np.count_nonzero(roi, axis=1)))
    low, high = 0, maximum_candidate
    best_component: np.ndarray | None = None
    while low < high:
        candidate = (low + high + 1) // 2
        component = _through_component(
            traversal_free,
            candidate,
            entrance,
            exit_area,
        )
        if component is None:
            high = candidate - 1
        else:
            low = candidate
            best_component = component

    if low > 0 and best_component is None:
        best_component = _through_component(
            traversal_free,
            low,
            entrance,
            exit_area,
        )

    # Bước 3: chọn lát cắt hẹp nhất thuộc tuyến liên thông để mô tả vị trí nút
    # thắt. Khi không còn đường cho một pixel, dùng lát cắt trống hẹp nhất.
    interior_rows = valid_rows[~opening_rows[valid_rows]]
    bottleneck_rows = interior_rows if interior_rows.size else valid_rows
    bottleneck_row = _find_bottleneck_row(
        free,
        best_component,
        bottleneck_rows,
    )
    roi_columns = np.flatnonzero(roi[bottleneck_row])
    left, right = int(roi_columns[0]), int(roi_columns[-1])
    free_ranges = _runs_to_world_ranges(
        _true_runs(free[bottleneck_row, left : right + 1]),
        left,
        minimum_world_x,
        pixels_per_meter,
    )

    # Bước 4: đóng gói dữ liệu theo mét; một pixel raster đại diện cho một ô
    # có bề rộng 1 / pixels_per_meter mét.
    return RouteCapacity(
        maximum_passable_width_meters=low / pixels_per_meter,
        walkway_width_meters=np.count_nonzero(roi[bottleneck_row]) / pixels_per_meter,
        bottleneck_y_meters=minimum_world_y + bottleneck_row / pixels_per_meter,
        bottleneck_free_x_ranges_meters=free_ranges,
        bottleneck_world_span=(
            minimum_world_x + left / pixels_per_meter,
            minimum_world_x + (right + 1) / pixels_per_meter,
        ),
        bottleneck_row=bottleneck_row,
    )


# ─────────────────────────────────────────────────────────────────────────────


def _through_component(
    free_mask: np.ndarray,
    width_pixels: int,
    entrance_mask: np.ndarray,
    exit_mask: np.ndarray,
) -> np.ndarray | None:
    """Trả component tâm đi xuyên suốt cho một bề rộng, hoặc None nếu không có."""
    if width_pixels < 1:
        return None

    # Bước 1: co free-space theo chiều X để biểu diễn các vị trí đặt tâm của
    # footprint có bề rộng đang kiểm tra.
    kernel = np.ones((1, width_pixels), dtype=np.uint8)
    navigable = cv2.erode(
        free_mask.astype(np.uint8),
        kernel,
        borderType=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    # Bước 2: một tuyến hợp lệ phải cùng chạm hàng vào và hàng ra.
    # Dùng 4-connectivity để không cho footprint lách chéo qua hai góc chỉ
    # tiếp xúc tại một điểm, vốn là trường hợp không an toàn ngoài thực tế.
    count, labels = cv2.connectedComponents(navigable, connectivity=4)
    if count <= 1:
        return None
    entrance_labels = set(int(value) for value in labels[entrance_mask] if value)
    exit_labels = set(int(value) for value in labels[exit_mask] if value)
    shared_labels = entrance_labels & exit_labels
    if not shared_labels:
        return None
    return labels == min(shared_labels)


# ─────────────────────────────────────────────────────────────────────────────


def _find_bottleneck_row(
    free_mask: np.ndarray,
    route_component: np.ndarray | None,
    valid_rows: np.ndarray,
) -> int:
    """Chọn hàng có khoảng trống hữu dụng hẹp nhất trên tuyến liên thông."""
    widths: list[int] = []
    rows: list[int] = []
    for row_value in valid_rows:
        row = int(row_value)
        runs = _true_runs(free_mask[row])
        if route_component is not None:
            route_columns = np.flatnonzero(route_component[row])
            if route_columns.size == 0:
                continue
            runs = tuple(
                (start, end)
                for start, end in runs
                if np.any((route_columns >= start) & (route_columns < end))
            )
        rows.append(row)
        widths.append(max((end - start for start, end in runs), default=0))

    # Chọn phần tử giữa của vùng nút thắt để nhãn ít nhảy khi nhiều hàng bằng nhau.
    minimum_width = min(widths)
    candidates = [row for row, width in zip(rows, widths) if width == minimum_width]
    return candidates[len(candidates) // 2]


# ─────────────────────────────────────────────────────────────────────────────


def _true_runs(values: np.ndarray) -> tuple[tuple[int, int], ...]:
    """Trả mọi đoạn True liên tục dưới dạng cặp đầu-cuối loại trừ."""
    padded = np.pad(np.asarray(values, dtype=np.int8), (1, 1))
    transitions = np.diff(padded)
    starts = np.flatnonzero(transitions == 1)
    ends = np.flatnonzero(transitions == -1)
    return tuple((int(start), int(end)) for start, end in zip(starts, ends))


# ─────────────────────────────────────────────────────────────────────────────


def _runs_to_world_ranges(
    runs: tuple[tuple[int, int], ...],
    offset: int,
    minimum_world_x: float,
    pixels_per_meter: float,
) -> tuple[tuple[float, float], ...]:
    """Chuyển các đoạn raster thành khoảng X loại trừ điểm cuối theo mét."""
    return tuple(
        (
            minimum_world_x + (offset + start) / pixels_per_meter,
            minimum_world_x + (offset + end) / pixels_per_meter,
        )
        for start, end in runs
    )
