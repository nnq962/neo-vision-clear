"""Điều phối việc chọn ROI, thu depth và tạo baseline."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Callable

import cv2
import numpy as np

from media_sources import MediaSources
from utils.logger import LOGGER
from walkway_monitor.calibration.baseline_builder import build_baseline
from walkway_monitor.calibration.roi_selector import (
    draw_roi,
    select_polygon,
    wait_for_empty_confirmation,
)
from walkway_monitor.calibration.storage import save_baseline
from walkway_monitor.config import CalibrationConfig
from walkway_monitor.depth.estimator import DepthEstimator
from walkway_monitor.models import BaselineArtifact, RoiDefinition
from walkway_monitor.ui import draw_text
from walkway_monitor.ui.detection_view import colorize_depth


class CalibrationPipeline:
    """Pipeline tạo baseline từ một nguồn RTSP hoặc video file."""

    def __init__(self, estimator: DepthEstimator, config: CalibrationConfig):
        """Lưu estimator và kiểm tra cấu hình calibration."""
        config.validate()
        self._estimator = estimator
        self._config = config

    # ─────────────────────────────────────────────────────────────────────────

    def run(
        self,
        source,
        output_path: str | Path,
        preview_path: str | Path | None = None,
        depth_preview_path: str | Path | None = None,
        roi: RoiDefinition | None = None,
        display: bool = True,
        stop_event: Event | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        **media_options,
    ) -> BaselineArtifact:
        """Chạy calibration và lưu baseline cùng các ảnh preview RGB, depth."""
        LOGGER.info("Bắt đầu calibration từ nguồn media.")
        try:
            with MediaSources(source, **media_options) as media:
                first_frame, first_meta = self._read_one(media)
                first_frame = resize_frame(first_frame, self._config.process_width)
                # Bước 1: API truyền ROI có sẵn; chỉ CLI tương tác mới tự chọn ROI.
                selected_roi = roi
                if selected_roi is None:
                    if not display:
                        raise ValueError("Chế độ headless yêu cầu ROI được cung cấp sẵn.")
                    selected_roi = select_polygon(first_frame)
                    wait_for_empty_confirmation(first_frame, selected_roi)

                # Bước 2: kiểm tra ROI theo kích thước frame thực tế trước khi suy luận.
                if np.count_nonzero(
                    selected_roi.to_mask(first_frame.shape[1], first_frame.shape[0])
                ) < 100:
                    raise ValueError("ROI quá nhỏ; hãy chọn vùng có ít nhất 100 pixel.")
                depth_maps = self._collect_depth_maps(
                    media,
                    first_frame.shape[:2],
                    selected_roi,
                    display=display,
                    stop_event=stop_event,
                    on_progress=on_progress,
                )
                artifact = build_baseline(
                    depth_maps=depth_maps,
                    roi=selected_roi,
                    config=self._config,
                    source_type=first_meta.source_type.name,
                )
        finally:
            # Chế độ API headless tuyệt đối không gọi API cửa sổ của OpenCV.
            if display:
                cv2.destroyAllWindows()

        saved_path = save_baseline(artifact, output_path)
        actual_preview = (
            Path(preview_path)
            if preview_path is not None
            else saved_path.with_suffix(".preview.jpg")
        )
        save_preview(first_frame, selected_roi, artifact, actual_preview)
        actual_depth_preview = (
            Path(depth_preview_path)
            if depth_preview_path is not None
            else saved_path.with_suffix(".depth.jpg")
        )
        save_reference_depth_preview(artifact, actual_depth_preview)
        LOGGER.info(
            "Calibration hoàn tất | noise_p99=%.6f | alignment_error=%.6f",
            artifact.noise_p99,
            artifact.alignment_median_error,
        )
        return artifact

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _read_one(media: MediaSources):
        """Đọc một batch đơn nguồn và trả về frame cùng metadata đầu tiên."""
        try:
            frames, metas = next(media)
        except StopIteration as exc:
            raise RuntimeError("Nguồn media kết thúc trước khi có frame.") from exc
        return frames[0], metas[0]

    # ─────────────────────────────────────────────────────────────────────────

    def _collect_depth_maps(
        self,
        media: MediaSources,
        expected_shape: tuple[int, int],
        roi: RoiDefinition,
        display: bool,
        stop_event: Event | None,
        on_progress: Callable[[int, int], None] | None,
    ) -> list[np.ndarray]:
        """Thu đúng số frame cấu hình và suy luận depth map cho từng frame."""
        depths: list[np.ndarray] = []
        window = "Dang thu baseline"
        while len(depths) < self._config.frame_count:
            # Bước 1: cho phép service dừng công việc khi server shutdown.
            if stop_event is not None and stop_event.is_set():
                raise InterruptedError("Calibration đã được yêu cầu dừng.")
            frame, _meta = self._read_one(media)
            frame = resize_frame(frame, self._config.process_width)
            if frame.shape[:2] != expected_shape:
                raise RuntimeError(
                    "Độ phân giải nguồn thay đổi trong lúc calibration: "
                    f"{frame.shape[:2]} != {expected_shape}."
                )
            depth = self._estimator.predict(frame)
            depths.append(depth)
            if on_progress is not None:
                on_progress(len(depths), self._config.frame_count)
            LOGGER.info(
                "Đã xử lý baseline frame %d/%d",
                len(depths),
                self._config.frame_count,
            )
            # Bước 2: preview tương tác chỉ dành cho lệnh CLI chạy có display.
            if display:
                preview = draw_roi(frame, roi)
                preview = draw_text(
                    preview,
                    f"BASELINE {len(depths)}/{self._config.frame_count} – Q: hủy",
                    (15, 8),
                    font_size=23,
                    color=(0, 255, 255),
                )
                cv2.imshow(window, preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    raise KeyboardInterrupt("Đã hủy khi đang thu baseline.")
        if display:
            cv2.destroyWindow(window)
        return depths


# ─────────────────────────────────────────────────────────────────────────────


def resize_frame(frame: np.ndarray, target_width: int) -> np.ndarray:
    """Thu nhỏ frame về target_width và không phóng lớn frame nhỏ hơn."""
    if target_width <= 0 or frame.shape[1] <= target_width:
        return frame
    scale = target_width / frame.shape[1]
    target_height = int(round(frame.shape[0] * scale))
    return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)


# ─────────────────────────────────────────────────────────────────────────────


def save_preview(
    frame: np.ndarray,
    roi: RoiDefinition,
    artifact: BaselineArtifact,
    path: str | Path,
) -> Path:
    """Lưu ảnh RGB có ROI và thống kê chính để kiểm tra calibration bằng mắt."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    preview = draw_roi(frame, roi)
    preview = draw_text(
        preview,
        f"Baseline: {artifact.frame_count} khung hình | nhiễu p99={artifact.noise_p99:.5f}",
        (15, 8),
        font_size=22,
        color=(0, 255, 255),
    )
    if not cv2.imwrite(str(output_path), preview):
        raise RuntimeError(f"Không thể lưu ảnh preview: {output_path}")
    LOGGER.info("Đã lưu ảnh preview: %s", output_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────


def save_reference_depth_preview(
    artifact: BaselineArtifact,
    path: str | Path,
) -> Path:
    """Tô màu và lưu reference depth thành ảnh để kiểm tra calibration."""
    artifact.validate()
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    preview = colorize_depth(
        artifact.reference_depth,
        artifact.reference_depth,
    )
    roi_points = artifact.roi.to_pixel_points(
        artifact.frame_width,
        artifact.frame_height,
    )
    cv2.polylines(
        preview,
        [roi_points],
        True,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )
    if not cv2.imwrite(str(output_path), preview):
        raise RuntimeError(f"Không thể lưu ảnh reference depth: {output_path}")
    LOGGER.info("Đã lưu ảnh reference depth: %s", output_path)
    return output_path
