"""Hiển thị kết quả detection, ROI và mask thay đổi trên OpenCV."""

from __future__ import annotations

import cv2
import numpy as np

from walkway_monitor.detection.models import DetectionOutput, OccupancyState
from walkway_monitor.models import BaselineArtifact
from walkway_monitor.ui.text import draw_text


_STATE_STYLE = {
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
    roi_mask = baseline.roi.to_mask(
        baseline.frame_width,
        baseline.frame_height,
    ) > 0
    padding = (output.check_area_mask > 0) & ~roi_mask
    padding_color = np.array([255, 255, 0])
    overlay[padding] = (
        0.75 * overlay[padding] + 0.25 * padding_color
    ).astype(np.uint8)
    changed = output.changed_mask > 0
    overlay[changed] = (
        0.35 * overlay[changed] + 0.65 * np.array([0, 0, 255])
    ).astype(np.uint8)
    points = baseline.roi.to_pixel_points(
        baseline.frame_width,
        baseline.frame_height,
    )
    check_area_contours, _hierarchy = cv2.findContours(
        output.check_area_mask.astype(np.uint8),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    cv2.drawContours(
        overlay,
        check_area_contours,
        -1,
        (255, 255, 0),
        2,
        cv2.LINE_AA,
    )
    if result.bottleneck_row is not None and result.bottleneck_span is not None:
        left, right = result.bottleneck_span
        cv2.line(
            overlay,
            (left, result.bottleneck_row),
            (right, result.bottleneck_row),
            (0, 165, 255),
            2,
            cv2.LINE_AA,
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
            f"Trống hẹp nhất: {result.minimum_free_width_ratio * 100:.1f}% | "
            f"Vật tại nút thắt: {result.obstacle_width_ratio * 100:.1f}% | "
            f"{fps:.1f} FPS"
        ),
        (15, 45),
        font_size=19,
        color=(255, 255, 255),
    )
    overlay = draw_text(
        overlay,
        (
            f"Diện tích vật lớn nhất: {result.largest_area_ratio * 100:.1f}% | "
            "Vạch cam: nút thắt | Viền xanh: check area"
        ),
        (15, 72),
        font_size=17,
        color=(255, 255, 255),
    )

    raw_depth_panel = colorize_depth(
        output.raw_depth,
        baseline.reference_depth,
    )
    raw_depth_panel[padding] = (
        0.75 * raw_depth_panel[padding] + 0.25 * padding_color
    ).astype(np.uint8)
    cv2.drawContours(
        raw_depth_panel,
        check_area_contours,
        -1,
        (255, 255, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.polylines(raw_depth_panel, [points], True, color, 2, cv2.LINE_AA)
    raw_depth_panel = draw_text(
        raw_depth_panel,
        "DEPTH THÔ TỪ MODEL",
        (15, 8),
        font_size=23,
        color=(255, 255, 255),
    )

    aligned_depth_panel = colorize_depth(
        output.aligned_depth,
        baseline.reference_depth,
    )
    aligned_depth_panel[padding] = (
        0.75 * aligned_depth_panel[padding] + 0.25 * padding_color
    ).astype(np.uint8)
    cv2.drawContours(
        aligned_depth_panel,
        check_area_contours,
        -1,
        (255, 255, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.polylines(aligned_depth_panel, [points], True, color, 2, cv2.LINE_AA)
    alignment_title = (
        "DEPTH CĂN CHỈNH ROBUST"
        if result.alignment_enabled
        else "DEPTH KHÔNG CĂN CHỈNH"
    )
    aligned_depth_panel = draw_text(
        aligned_depth_panel,
        alignment_title,
        (15, 8),
        font_size=23,
        color=(255, 255, 255),
    )
    alignment_details = (
        f"scale={result.alignment_scale:.5f} | "
        f"shift={result.alignment_shift:.5f} | "
        f"fit={result.alignment_inlier_ratio * 100:.0f}%"
        if result.alignment_enabled
        else "alignment=OFF | scale=1.00000 | shift=0.00000"
    )
    aligned_depth_panel = draw_text(
        aligned_depth_panel,
        alignment_details,
        (15, 42),
        font_size=19,
        color=(255, 255, 255),
    )
    return cv2.hconcat([overlay, raw_depth_panel, aligned_depth_panel])


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
