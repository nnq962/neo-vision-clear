"""Hiển thị kết quả detection, ROI và mask thay đổi trên OpenCV."""

from __future__ import annotations

import cv2
import numpy as np

from walkway_monitor.detection.models import DetectionOutput, OccupancyState
from walkway_monitor.models import BaselineArtifact
from walkway_monitor.ui.text import draw_text


_STATE_STYLE = {
    OccupancyState.UNKNOWN: ("KHÔNG XÁC ĐỊNH", (0, 255, 255)),
    OccupancyState.CLEAR: ("LỐI ĐI TRỐNG", (0, 200, 0)),
    OccupancyState.OCCUPIED: ("CÓ VẬT CẢN", (0, 0, 255)),
}


def render_detection_view(
    frame: np.ndarray,
    baseline: BaselineArtifact,
    output: DetectionOutput,
    fps: float,
) -> np.ndarray:
    """Tạo ảnh ghép gồm frame overlay và changed mask để theo dõi detector."""
    result = output.result
    label, color = _STATE_STYLE[result.state]
    overlay = frame.copy()
    changed = output.changed_mask > 0
    overlay[changed] = (
        0.35 * overlay[changed] + 0.65 * np.array([0, 0, 255])
    ).astype(np.uint8)
    points = baseline.roi.to_pixel_points(
        baseline.frame_width,
        baseline.frame_height,
    )
    cv2.polylines(overlay, [points], True, color, 3, cv2.LINE_AA)
    overlay = draw_text(
        overlay,
        label,
        (15, 8),
        font_size=28,
        color=color,
        stroke_width=2,
    )
    overlay = draw_text(
        overlay,
        (
            f"Vùng lớn nhất: {result.largest_area_ratio * 100:.2f}% | "
            f"Ngoài ROI: {result.outside_change_ratio * 100:.2f}% | {fps:.1f} FPS"
        ),
        (15, 45),
        font_size=19,
        color=(255, 255, 255),
    )

    depth_panel = colorize_depth(
        output.aligned_depth,
        baseline.reference_depth,
    )
    cv2.polylines(depth_panel, [points], True, color, 2, cv2.LINE_AA)
    depth_panel = draw_text(
        depth_panel,
        "BẢN ĐỒ NHIỆT DEPTH ANYTHING",
        (15, 8),
        font_size=23,
        color=(255, 255, 255),
    )
    return cv2.hconcat([overlay, depth_panel])


# ─────────────────────────────────────────────────────────────────────────────


def colorize_depth(depth: np.ndarray, reference_depth: np.ndarray) -> np.ndarray:
    """Tạo heatmap depth ổn định bằng dải percentile cố định của baseline."""
    if depth.shape != reference_depth.shape or depth.ndim != 2:
        raise ValueError("Depth hiện tại và reference phải là mảng 2D cùng kích thước.")
    reference_values = reference_depth[np.isfinite(reference_depth)]
    lower = float(np.percentile(reference_values, 2.0))
    upper = float(np.percentile(reference_values, 98.0))
    span = max(upper - lower, 1e-6)
    normalized = np.clip((depth - lower) / span, 0.0, 1.0)
    depth_u8 = np.rint(normalized * 255.0).astype(np.uint8)
    return cv2.applyColorMap(depth_u8, cv2.COLORMAP_TURBO)
