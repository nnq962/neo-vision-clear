"""Pipeline gom một frame mới nhất từ mỗi camera vào cùng một batch depth."""

from __future__ import annotations

import threading
import time
from typing import Callable, Sequence

import cv2
import numpy as np

from media_sources import MediaSources
from utils.logger import LOGGER
from walkway_monitor.config import DetectionConfig
from walkway_monitor.depth.estimator import DepthEstimator, predict_depth_batch
from walkway_monitor.detection.detector import WalkwayAnalyzer
from walkway_monitor.detection.models import CorridorSnapshot, DetectionOutput
from walkway_monitor.detection.pipeline import resize_to_baseline
from walkway_monitor.models import BaselineArtifact
from walkway_monitor.ui import DetectionViewRenderer


CameraSnapshotCallback = Callable[[int, CorridorSnapshot], None]
CameraOutputCallback = Callable[[int, DetectionOutput], None]


class CameraBatchDetectionPipeline:
    """Dùng chung model depth cho một hoặc nhiều camera có baseline độc lập."""

    def __init__(
        self,
        estimator: DepthEstimator,
        baselines: Sequence[BaselineArtifact],
        config: DetectionConfig,
        display: bool = True,
        show_depth_heatmaps: bool = True,
        log_interval: float = 2.0,
    ) -> None:
        """Khởi tạo analyzer và renderer riêng cho từng camera."""
        normalized_baselines = tuple(baselines)
        if not normalized_baselines:
            raise ValueError("Batch camera cần ít nhất một baseline.")
        if log_interval < 0:
            raise ValueError("log_interval không được âm.")
        self._validate_compatibility(normalized_baselines)

        self._estimator = estimator
        self._baselines = normalized_baselines
        self._analyzers = tuple(
            WalkwayAnalyzer(baseline, config) for baseline in self._baselines
        )
        self._renderers = (
            tuple(DetectionViewRenderer(baseline) for baseline in self._baselines)
            if display
            else ()
        )
        self._display = display
        self._show_depth_heatmaps = show_depth_heatmaps
        self._log_interval = log_interval

    # ─────────────────────────────────────────────────────────────────────────

    def run(
        self,
        sources: Sequence[str | int],
        *,
        stop_event: threading.Event | None = None,
        on_snapshot: CameraSnapshotCallback | None = None,
        on_output: CameraOutputCallback | None = None,
        **media_options,
    ) -> int:
        """Xử lý đồng bộ frame mới nhất của mọi RTSP cho tới khi dừng."""
        normalized_sources = list(sources)
        if len(normalized_sources) != len(self._baselines):
            raise ValueError("Mỗi source phải có đúng một baseline tương ứng.")

        processed_frames = 0
        processed_batches = 0
        run_started = time.perf_counter()
        last_batch_time = run_started
        smooth_camera_fps = 0.0
        window_started = run_started
        window_batches = 0
        window_source_time = 0.0
        window_resize_time = 0.0
        window_inference_time = 0.0
        window_analysis_time = 0.0
        window_publish_time = 0.0
        window_render_time = 0.0
        latest_snapshots: tuple[CorridorSnapshot, ...] = ()
        LOGGER.info(
            "Bắt đầu phân tích %d camera trong một batch model.",
            len(normalized_sources),
        )

        try:
            with MediaSources(normalized_sources, **media_options) as media:
                media_iterator = iter(media)
                while True:
                    # Bước 1: reader trả đúng một frame mới nhất từ mỗi camera.
                    source_started = time.perf_counter()
                    try:
                        frames, _metas = next(media_iterator)
                    except StopIteration:
                        break
                    source_time = time.perf_counter() - source_started
                    if stop_event is not None and stop_event.is_set():
                        break
                    if len(frames) != len(self._baselines):
                        raise RuntimeError("Reader trả về sai số frame camera.")

                    # Bước 2: mỗi frame được đưa về hệ pixel của baseline riêng.
                    resize_started = time.perf_counter()
                    resized_frames = [
                        resize_to_baseline(frame, baseline)
                        for frame, baseline in zip(frames, self._baselines)
                    ]
                    resize_time = time.perf_counter() - resize_started

                    # Bước 3: toàn bộ camera dùng chung đúng một forward model.
                    inference_started = time.perf_counter()
                    depths = predict_depth_batch(self._estimator, resized_frames)
                    inference_time = time.perf_counter() - inference_started

                    # Bước 4: phân tích bằng baseline tương ứng, không trộn state.
                    analysis_started = time.perf_counter()
                    outputs = tuple(
                        analyzer.process(depth)
                        for analyzer, depth in zip(self._analyzers, depths)
                    )
                    analysis_time = time.perf_counter() - analysis_started
                    latest_snapshots = tuple(output.snapshot for output in outputs)

                    publish_started = time.perf_counter()
                    for camera_index, output in enumerate(outputs):
                        if on_snapshot is not None:
                            on_snapshot(camera_index, output.snapshot)
                        if on_output is not None:
                            on_output(camera_index, output)
                    publish_time = time.perf_counter() - publish_started

                    processed_batches += 1
                    processed_frames += len(outputs)
                    now = time.perf_counter()
                    instant_camera_fps = 1.0 / max(now - last_batch_time, 1e-6)
                    smooth_camera_fps = (
                        instant_camera_fps
                        if smooth_camera_fps == 0.0
                        else 0.9 * smooth_camera_fps + 0.1 * instant_camera_fps
                    )
                    last_batch_time = now

                    # Bước 5: render các camera rồi đọc phím một lần cho cả batch.
                    render_started = time.perf_counter()
                    should_stop = self._show_batch(
                        resized_frames,
                        outputs,
                        smooth_camera_fps,
                    ) if self._display else False
                    render_time = time.perf_counter() - render_started

                    window_batches += 1
                    window_source_time += source_time
                    window_resize_time += resize_time
                    window_inference_time += inference_time
                    window_analysis_time += analysis_time
                    window_publish_time += publish_time
                    window_render_time += render_time
                    log_time = time.perf_counter()
                    window_elapsed = log_time - window_started
                    if self._log_interval > 0 and window_elapsed >= self._log_interval:
                        self._log_performance(
                            batches=window_batches,
                            camera_count=len(self._baselines),
                            elapsed=window_elapsed,
                            source_time=window_source_time,
                            resize_time=window_resize_time,
                            inference_time=window_inference_time,
                            analysis_time=window_analysis_time,
                            publish_time=window_publish_time,
                            render_time=window_render_time,
                            snapshots=latest_snapshots,
                        )
                        window_started = log_time
                        window_batches = 0
                        window_source_time = 0.0
                        window_resize_time = 0.0
                        window_inference_time = 0.0
                        window_analysis_time = 0.0
                        window_publish_time = 0.0
                        window_render_time = 0.0
                    if should_stop:
                        break
        finally:
            if self._display:
                cv2.destroyAllWindows()

        total_elapsed = max(time.perf_counter() - run_started, 1e-6)
        LOGGER.info(
            "Batch camera đã dừng sau %d batch/%d frame | FPS mỗi camera=%.2f.",
            processed_batches,
            processed_frames,
            processed_batches / total_elapsed,
        )
        return processed_frames

    # ─────────────────────────────────────────────────────────────────────────

    def _show_batch(
        self,
        frames: Sequence[np.ndarray],
        outputs: Sequence[DetectionOutput],
        fps: float,
    ) -> bool:
        """Hiển thị từng camera trong cửa sổ riêng và đọc phím dừng một lần."""
        for camera_index, (renderer, frame, output) in enumerate(
            zip(self._renderers, frames, outputs),
            start=1,
        ):
            view = renderer.render(
                frame,
                output,
                fps,
                show_depth_heatmaps=self._show_depth_heatmaps,
            )
            cv2.imshow(f"Walkway measurements - camera {camera_index}", view)
        key = cv2.waitKey(1) & 0xFF
        return key in (27, ord("q"), ord("Q"))

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _log_performance(
        batches: int,
        camera_count: int,
        elapsed: float,
        source_time: float,
        resize_time: float,
        inference_time: float,
        analysis_time: float,
        publish_time: float,
        render_time: float,
        snapshots: Sequence[CorridorSnapshot],
    ) -> None:
        """Ghi throughput, thời gian batch và phép đo mới nhất từng camera."""
        batch_count = max(batches, 1)
        frame_count = max(batches * camera_count, 1)
        measurements = " | ".join(
            f"cam{index}=({snapshot.maximum_passable_width_meters:.2f}m/"
            f"{snapshot.walkway_width_meters:.2f}m)"
            for index, snapshot in enumerate(snapshots, start=1)
        )
        LOGGER.info(
            "FPS/camera=%.2f | FPS tổng=%.2f | batch=%d | "
            "source=%.1fms/batch | resize=%.1fms/frame | "
            "inference=%.1fms/batch (%.1fms/frame) | "
            "analysis=%.1fms/frame | publish=%.1fms/frame | "
            "render=%.1fms/frame | %s",
            batches / max(elapsed, 1e-6),
            frame_count / max(elapsed, 1e-6),
            camera_count,
            source_time * 1000 / batch_count,
            resize_time * 1000 / frame_count,
            inference_time * 1000 / batch_count,
            inference_time * 1000 / frame_count,
            analysis_time * 1000 / frame_count,
            publish_time * 1000 / frame_count,
            render_time * 1000 / frame_count,
            measurements,
        )

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_compatibility(
        baselines: Sequence[BaselineArtifact],
    ) -> None:
        """Bảo đảm các baseline có thể dùng chung model và tensor batch."""
        first = baselines[0]
        first_ratio = first.frame_width / first.frame_height
        for baseline in baselines[1:]:
            if baseline.encoder != first.encoder or baseline.input_size != first.input_size:
                raise ValueError(
                    "Các baseline trong batch phải cùng encoder và input_size."
                )
            ratio = baseline.frame_width / baseline.frame_height
            if abs(ratio - first_ratio) / first_ratio > 0.02:
                raise ValueError(
                    "Các baseline trong batch phải có cùng tỷ lệ khung hình."
                )
