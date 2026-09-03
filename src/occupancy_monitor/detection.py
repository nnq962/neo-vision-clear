"""Các thuật toán tạo mask và ổn định trạng thái chiếm dụng."""

from __future__ import annotations

import cv2
import numpy as np


class StableState:
    """Chống nhiễu trạng thái bằng số frame xác nhận liên tiếp."""

    def __init__(self, enter_frames: int, exit_frames: int) -> None:
        """Khởi tạo số frame cần thiết để vào và thoát trạng thái occupied."""
        self.enter_frames = enter_frames
        self.exit_frames = exit_frames
        self.occupied = False
        self.positive_count = 0
        self.negative_count = 0

    # ─────────────────────────────────────────────────────────────────────────
    def update(self, detected: bool) -> bool:
        """Cập nhật một kết quả frame và trả về trạng thái đã ổn định."""
        if detected:
            self.positive_count += 1
            self.negative_count = 0
            if self.positive_count >= self.enter_frames:
                self.occupied = True
        else:
            self.negative_count += 1
            self.positive_count = 0
            if self.negative_count >= self.exit_frames:
                self.occupied = False
        return self.occupied


# ─────────────────────────────────────────────────────────────────────────────
def preprocess(image: np.ndarray) -> np.ndarray:
    """Giảm nhiễu camera và chuyển ảnh sang không gian màu Lab."""
    blurred = cv2.GaussianBlur(image, (5, 5), 0)
    return cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB)


# ─────────────────────────────────────────────────────────────────────────────
def lab_color_distance(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Tính khoảng cách Euclid Lab theo từng pixel dưới dạng ảnh 8-bit."""
    delta = first.astype(np.float32) - second.astype(np.float32)
    distance = np.sqrt(np.sum(delta * delta, axis=2))
    return np.clip(distance, 0, 255).astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
def foreground_mask(
    background_roi: np.ndarray,
    current_roi: np.ndarray,
    pixel_threshold: int,
    min_contour_area: int,
    roi_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Tạo mask nhị phân cho các vùng đủ khác nền và đủ lớn."""
    difference = lab_color_distance(
        preprocess(background_roi), preprocess(current_roi)
    )
    _, raw_mask = cv2.threshold(
        difference, pixel_threshold, 255, cv2.THRESH_BINARY
    )
    if roi_mask is not None:
        raw_mask = cv2.bitwise_and(raw_mask, roi_mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    filtered = np.zeros_like(mask)
    for contour in contours:
        if cv2.contourArea(contour) >= min_contour_area:
            cv2.drawContours(filtered, [contour], -1, 255, thickness=cv2.FILLED)
    if roi_mask is not None:
        filtered = cv2.bitwise_and(filtered, roi_mask)
    return filtered


# ─────────────────────────────────────────────────────────────────────────────
def changed_ratio(mask: np.ndarray, roi_mask: np.ndarray | None = None) -> float:
    """Tính tỷ lệ pixel foreground trên diện tích hợp lệ của ROI."""
    valid_pixels = cv2.countNonZero(roi_mask) if roi_mask is not None else mask.size
    if valid_pixels == 0:
        return 0.0
    return cv2.countNonZero(mask) / float(valid_pixels)
