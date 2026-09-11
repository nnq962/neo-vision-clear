"""Hiển thị camera, BEV và các heatmap depth trên lưới OpenCV."""

from __future__ import annotations

import cv2
import numpy as np

from walkway_monitor.detection.models import DetectionOutput
from walkway_monitor.models import BaselineArtifact
from walkway_monitor.ui.bev_view import BevRenderer
from walkway_monitor.ui.text import draw_text


_ROI_COLOR = (0, 255, 255)
_PADDING_COLOR = np.array([255, 255, 0])


class DetectionViewRenderer:
    """Render giao diện debug và cache toàn bộ hình học cố định của baseline."""

    def __init__(self, baseline: BaselineArtifact):
        """Chuẩn bị ROI, polygon và renderer BEV dùng lại giữa các frame."""
        self._baseline = baseline
        self._roi_mask = baseline.roi.to_mask(
            baseline.frame_width,
            baseline.frame_height,
        ) > 0
        self._points = baseline.roi.to_pixel_points(
            baseline.frame_width,
            baseline.frame_height,
        )
        world = baseline.roi.world_coordinates
        if world is None:
            raise ValueError("Baseline thiếu tọa độ thực để hiển thị giao diện.")
        self._world_points = world.points
        self._world_unit = world.unit
        self._bev = BevRenderer(
            baseline,
            baseline.frame_width,
            baseline.frame_height,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def render(
        self,
        frame: np.ndarray,
        output: DetectionOutput,
        fps: float,
        show_depth_heatmaps: bool = True,
    ) -> np.ndarray:
        """Tạo lưới camera, BEV và hai panel depth tùy theo cấu hình."""
        # Bước 1: chuẩn bị các vùng và contour dùng chung cho ba panel camera.
        padding = (output.check_area_mask > 0) & ~self._roi_mask
        contours, _hierarchy = cv2.findContours(
            output.check_area_mask.astype(np.uint8),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        # Bước 2: tạo panel camera với mask đỏ và lát cắt nút thắt màu cam.
        camera_panel = self._render_camera_panel(
            frame,
            output,
            padding,
            contours,
            fps,
        )
        bev_panel = self._bev.render(frame, output)
        top_row = cv2.hconcat([camera_panel, bev_panel])
        if not show_depth_heatmaps:
            return top_row

        # Bước 3: tạo hai heatmap với cùng lớp ROI và check area.
        raw_panel = self._render_depth_panel(
            output.raw_depth,
            "DEPTH THÔ TỪ MODEL",
            padding,
            contours,
        )
        diagnostics = output.diagnostics
        alignment_title = (
            "DEPTH CĂN CHỈNH ROBUST"
            if diagnostics.alignment_enabled
            else "DEPTH KHÔNG CĂN CHỈNH"
        )
        aligned_panel = self._render_depth_panel(
            output.aligned_depth,
            alignment_title,
            padding,
            contours,
        )
        alignment_details = (
            f"scale={diagnostics.alignment_scale:.5f} | "
            f"shift={diagnostics.alignment_shift:.5f} | "
            f"fit={diagnostics.alignment_inlier_ratio * 100:.0f}%"
            if diagnostics.alignment_enabled
            else "alignment=OFF | scale=1.00000 | shift=0.00000"
        )
        aligned_panel = draw_text(
            aligned_panel,
            alignment_details,
            (15, 42),
            font_size=19,
            color=(255, 255, 255),
        )
        return cv2.vconcat([top_row, cv2.hconcat([raw_panel, aligned_panel])])

    # ─────────────────────────────────────────────────────────────────────────

    def _render_camera_panel(
        self,
        frame: np.ndarray,
        output: DetectionOutput,
        padding: np.ndarray,
        contours: tuple[np.ndarray, ...],
        fps: float,
    ) -> np.ndarray:
        """Vẽ ROI, mask thay đổi và nút thắt lên ảnh camera."""
        overlay = frame.copy()
        overlay[padding] = (
            0.75 * overlay[padding] + 0.25 * _PADDING_COLOR
        ).astype(np.uint8)
        changed = output.changed_mask > 0
        overlay[changed] = (
            0.35 * overlay[changed] + 0.65 * np.array([0, 0, 255])
        ).astype(np.uint8)
        self._draw_geometry(overlay, contours, thickness=3)
        overlay = self._draw_camera_coordinate_labels(overlay)
        start, end = np.rint(
            self._bev.camera_bottleneck_line(output)
        ).astype(np.int32)
        cv2.line(overlay, tuple(start), tuple(end), (0, 165, 255), 2, cv2.LINE_AA)
        overlay = draw_text(
            overlay,
            "CAMERA / MASK THAY ĐỔI",
            (15, 8),
            font_size=23,
            color=(255, 255, 255),
            stroke_width=2,
        )
        return draw_text(
            overlay,
            f"{fps:.1f} FPS",
            (15, 40),
            font_size=18,
            color=(255, 255, 255),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _draw_camera_coordinate_labels(self, panel: np.ndarray) -> np.ndarray:
        """Vẽ nhãn tọa độ thực tại các đỉnh ROI trên ảnh camera."""
        canvas = panel
        height, width = panel.shape[:2]

        # Ghép tọa độ pixel và tọa độ mét theo đúng thứ tự P1, P2, ...
        for index, (pixel_point, world_point) in enumerate(
            zip(self._points, self._world_points)
        ):
            pixel_x, pixel_y = int(pixel_point[0]), int(pixel_point[1])
            cv2.circle(canvas, (pixel_x, pixel_y), 5, _ROI_COLOR, -1, cv2.LINE_AA)
            label_x = min(max(pixel_x + 8, 0), max(width - 175, 0))
            label_y = min(max(pixel_y + 8, 0), max(height - 18, 0))
            canvas = draw_text(
                canvas,
                (
                    f"P{index + 1} "
                    f"({world_point[0]:.2f}, {world_point[1]:.2f}) "
                    f"{self._world_unit}"
                ),
                (label_x, label_y),
                font_size=15,
                color=_ROI_COLOR,
                stroke_width=2,
            )
        return canvas

    # ─────────────────────────────────────────────────────────────────────────

    def _render_depth_panel(
        self,
        depth: np.ndarray,
        title: str,
        padding: np.ndarray,
        contours: tuple[np.ndarray, ...],
    ) -> np.ndarray:
        """Tạo một heatmap depth có cùng lớp đánh dấu hình học."""
        panel = colorize_depth(depth, self._baseline.reference_depth)
        panel[padding] = (
            0.75 * panel[padding] + 0.25 * _PADDING_COLOR
        ).astype(np.uint8)
        self._draw_geometry(panel, contours, thickness=2)
        return draw_text(
            panel,
            title,
            (15, 8),
            font_size=23,
            color=(255, 255, 255),
        )

    # ─────────────────────────────────────────────────────────────────────────

    def _draw_geometry(
        self,
        panel: np.ndarray,
        contours: tuple[np.ndarray, ...],
        thickness: int,
    ) -> None:
        """Vẽ check area và polygon ROI lên một panel camera."""
        cv2.drawContours(
            panel,
            contours,
            -1,
            (255, 255, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.polylines(
            panel,
            [self._points],
            True,
            _ROI_COLOR,
            thickness,
            cv2.LINE_AA,
        )


# ─────────────────────────────────────────────────────────────────────────────


def render_detection_view(
    frame: np.ndarray,
    baseline: BaselineArtifact,
    output: DetectionOutput,
    fps: float,
    show_depth_heatmaps: bool = True,
) -> np.ndarray:
    """Render một frame độc lập; pipeline realtime nên tái sử dụng renderer."""
    renderer = DetectionViewRenderer(baseline)
    return renderer.render(frame, output, fps, show_depth_heatmaps)


# ─────────────────────────────────────────────────────────────────────────────


def colorize_depth(depth: np.ndarray, reference_depth: np.ndarray) -> np.ndarray:
    """Tạo heatmap depth ổn định bằng dải percentile cố định của baseline."""
    if depth.shape != reference_depth.shape or depth.ndim != 2:
        raise ValueError("Depth hiện tại và reference phải là mảng 2D cùng kích thước.")

    # Bước 1: dùng percentile baseline cố định để màu không thay đổi giữa frame.
    reference_values = reference_depth[np.isfinite(reference_depth)]
    lower = float(np.percentile(reference_values, 2.0))
    upper = float(np.percentile(reference_values, 98.0))
    span = max(upper - lower, 1e-6)

    # Bước 2: chuẩn hóa depth sang uint8 và áp colormap Turbo.
    normalized = np.clip((depth - lower) / span, 0.0, 1.0)
    depth_u8 = np.rint(normalized * 255.0).astype(np.uint8)
    return cv2.applyColorMap(depth_u8, cv2.COLORMAP_TURBO)
