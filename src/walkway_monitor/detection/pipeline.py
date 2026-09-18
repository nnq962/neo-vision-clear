"""Pipeline đọc full frame, suy luận depth và hiển thị phép đo lối đi."""

from __future__ import annotations

import threading
import time
from typing import Callable

import cv2
import numpy as np

from media_sources import MediaSources
from utils.logger import LOGGER
from walkway_monitor.config import DetectionConfig
from walkway_monitor.depth.estimator import DepthEstimator
from walkway_monitor.detection.detector import WalkwayAnalyzer
from walkway_monitor.detection.models import CorridorSnapshot, DetectionOutput
from walkway_monitor.models import BaselineArtifact
from walkway_monitor.ui import DetectionViewRenderer


class DetectionPipeline:
    """Điều phối nguồn media, model depth, detector và cửa sổ debug."""

    def __init__(
        self,
        estimator: DepthEstimator,
        baseline: BaselineArtifact,
        config: DetectionConfig,
        display: bool = True,
        show_depth_heatmaps: bool = True,
        log_interval: float = 2.0,
    ):
        """Khởi tạo analyzer và lưu các dependency chạy realtime."""
        if log_interval < 0:
            raise ValueError("log_interval không được âm.")
        self._estimator = estimator
        self._baseline = baseline
        self._analyzer = WalkwayAnalyzer(baseline, config)
        self._renderer = DetectionViewRenderer(baseline) if display else None
        self._display = display
        self._show_depth_heatmaps = show_depth_heatmaps
        self._log_interval = log_interval

    # ─────────────────────────────────────────────────────────────────────────

    def run(
        self,
        source,
        *,
        stop_event: threading.Event | None = None,
        on_snapshot: Callable[[CorridorSnapshot], None] | None = None,
        on_output: Callable[[DetectionOutput], None] | None = None,
        **media_options,
    ) -> int:
        """Xử lý nguồn tới khi video kết thúc hoặc người dùng nhấn Q/Esc."""
        processed_frames = 0
        smooth_fps = 0.0
        run_started = time.perf_counter()
        last_time = run_started
        window_started = run_started
        window_frames = 0
        window_source_time = 0.0
        window_resize_time = 0.0
        window_inference_time = 0.0
        window_analysis_time = 0.0
        window_alignment_time = 0.0
        window_mask_time = 0.0
        window_bev_time = 0.0
        window_publish_time = 0.0
        window_render_time = 0.0
        LOGGER.info(
            "Bắt đầu phân tích full frame ở độ phân giải %dx%d.",
            self._baseline.frame_width,
            self._baseline.frame_height,
        )
        try:
            with MediaSources(source, **media_options) as media:
                media_iterator = iter(media)
                while True:
                    # Bước 1: đo cả thời gian chờ/giải mã frame trong reader.
                    source_started = time.perf_counter()
                    try:
                        frames, _metas = next(media_iterator)
                    except StopIteration:
                        break
                    source_time = time.perf_counter() - source_started

                    # Cho phép lifespan của server dừng worker mà không phải
                    # kết thúc cưỡng bức process đang chạy.
                    if stop_event is not None and stop_event.is_set():
                        break
                    resize_started = time.perf_counter()
                    frame = resize_to_baseline(frames[0], self._baseline)
                    resize_time = time.perf_counter() - resize_started

                    inference_started = time.perf_counter()
                    depth = self._estimator.predict(frame)
                    inference_time = time.perf_counter() - inference_started

                    output = self._analyzer.process(depth)
                    analysis_time = output.timings.total_seconds

                    # Bước 2: callback có thể gồm contour, khóa snapshot hoặc
                    # tích hợp bên ngoài nên được đo riêng khỏi analyzer.
                    publish_started = time.perf_counter()
                    if on_snapshot is not None:
                        on_snapshot(output.snapshot)
                    if on_output is not None:
                        on_output(output)
                    publish_time = time.perf_counter() - publish_started
                    processed_frames += 1

                    now = time.perf_counter()
                    instant_fps = 1.0 / max(now - last_time, 1e-6)
                    smooth_fps = (
                        instant_fps
                        if smooth_fps == 0.0
                        else 0.9 * smooth_fps + 0.1 * instant_fps
                    )
                    last_time = now
                    render_time = 0.0
                    should_stop = False
                    if self._display:
                        render_started = time.perf_counter()
                        should_stop = self._show(frame, output, smooth_fps)
                        render_time = time.perf_counter() - render_started

                    window_frames += 1
                    window_source_time += source_time
                    window_resize_time += resize_time
                    window_inference_time += inference_time
                    window_analysis_time += analysis_time
                    window_alignment_time += output.timings.alignment_seconds
                    window_mask_time += output.timings.mask_seconds
                    window_bev_time += output.timings.bev_seconds
                    window_publish_time += publish_time
                    window_render_time += render_time
                    log_time = time.perf_counter()
                    window_elapsed = log_time - window_started
                    if (
                        self._log_interval > 0
                        and window_elapsed >= self._log_interval
                    ):
                        self._log_performance(
                            frames=window_frames,
                            elapsed=window_elapsed,
                            source_time=window_source_time,
                            resize_time=window_resize_time,
                            inference_time=window_inference_time,
                            analysis_time=window_analysis_time,
                            alignment_time=window_alignment_time,
                            mask_time=window_mask_time,
                            bev_time=window_bev_time,
                            publish_time=window_publish_time,
                            render_time=window_render_time,
                            snapshot=output.snapshot,
                        )
                        window_started = log_time
                        window_frames = 0
                        window_source_time = 0.0
                        window_resize_time = 0.0
                        window_inference_time = 0.0
                        window_analysis_time = 0.0
                        window_alignment_time = 0.0
                        window_mask_time = 0.0
                        window_bev_time = 0.0
                        window_publish_time = 0.0
                        window_render_time = 0.0
                    if should_stop:
                        break
        finally:
            if self._display:
                cv2.destroyAllWindows()
        total_elapsed = max(time.perf_counter() - run_started, 1e-6)
        LOGGER.info(
            "Phân tích đã dừng sau %d frame | FPS trung bình=%.2f.",
            processed_frames,
            processed_frames / total_elapsed,
        )
        return processed_frames

    # ─────────────────────────────────────────────────────────────────────────

    def _show(
        self,
        frame: np.ndarray,
        output: DetectionOutput,
        fps: float,
    ) -> bool:
        """Hiển thị kết quả và trả True khi người dùng yêu cầu dừng."""
        if self._renderer is None:
            raise RuntimeError("Renderer chưa được khởi tạo khi display đang bật.")
        view = self._renderer.render(
            frame,
            output,
            fps,
            show_depth_heatmaps=self._show_depth_heatmaps,
        )
        cv2.imshow("Walkway measurements", view)
        key = cv2.waitKey(1) & 0xFF
        return key in (27, ord("q"), ord("Q"))

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _log_performance(
        frames: int,
        elapsed: float,
        source_time: float,
        resize_time: float,
        inference_time: float,
        analysis_time: float,
        alignment_time: float,
        mask_time: float,
        bev_time: float,
        publish_time: float,
        render_time: float,
        snapshot: CorridorSnapshot,
    ) -> None:
        """Ghi hiệu năng và snapshot mới nhất trong một cửa sổ thời gian."""
        frame_count = max(frames, 1)
        measured_analysis_time = alignment_time + mask_time + bev_time
        other_analysis_time = max(analysis_time - measured_analysis_time, 0.0)
        performance = (
            f"FPS={frames / max(elapsed, 1e-6):.2f} | "
            f"source={source_time * 1000 / frame_count:.1f}ms | "
            f"resize={resize_time * 1000 / frame_count:.1f}ms | "
            f"inference={inference_time * 1000 / frame_count:.1f}ms | "
            f"analysis={analysis_time * 1000 / frame_count:.1f}ms "
            f"(align={alignment_time * 1000 / frame_count:.1f}, "
            f"mask={mask_time * 1000 / frame_count:.1f}, "
            f"bev={bev_time * 1000 / frame_count:.1f}, "
            f"other={other_analysis_time * 1000 / frame_count:.1f}) | "
            f"publish={publish_time * 1000 / frame_count:.1f}ms | "
            f"render={render_time * 1000 / frame_count:.1f}ms"
        )
        LOGGER.info(
            "%s | bề rộng đi xuyên suốt=%.2fm/%.2fm | nút thắt Y=%.2fm",
            performance,
            snapshot.maximum_passable_width_meters,
            snapshot.walkway_width_meters,
            snapshot.bottleneck_y_meters,
        )


# ─────────────────────────────────────────────────────────────────────────────


def resize_to_baseline(frame: np.ndarray, baseline: BaselineArtifact) -> np.ndarray:
    """Kiểm tra tỷ lệ rồi resize full frame về đúng độ phân giải baseline."""
    if not isinstance(frame, np.ndarray) or frame.ndim != 3:
        raise ValueError("Frame nguồn phải là numpy.ndarray ba chiều.")
    source_height, source_width = frame.shape[:2]
    source_ratio = source_width / source_height
    baseline_ratio = baseline.frame_width / baseline.frame_height
    ratio_error = abs(source_ratio - baseline_ratio) / baseline_ratio
    if ratio_error > 0.02:
        raise RuntimeError(
            "Tỷ lệ khung hình nguồn không khớp baseline: "
            f"{source_width}x{source_height} so với "
            f"{baseline.frame_width}x{baseline.frame_height}."
        )
    target_size = (baseline.frame_width, baseline.frame_height)
    if (source_width, source_height) == target_size:
        return frame
    interpolation = (
        cv2.INTER_AREA
        if source_width > baseline.frame_width
        else cv2.INTER_LINEAR
    )
    return cv2.resize(frame, target_size, interpolation=interpolation)
