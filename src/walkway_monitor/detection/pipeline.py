"""Pipeline đọc full frame, suy luận depth và hiển thị trạng thái lối đi."""

from __future__ import annotations

import time

import cv2
import numpy as np

from media_sources import MediaSources
from utils.logger import LOGGER
from walkway_monitor.config import DetectionConfig
from walkway_monitor.depth.estimator import DepthEstimator
from walkway_monitor.detection.detector import OccupancyDetector
from walkway_monitor.detection.models import DetectionOutput, OccupancyState
from walkway_monitor.models import BaselineArtifact
from walkway_monitor.ui import render_detection_view


class DetectionPipeline:
    """Điều phối nguồn media, model depth, detector và cửa sổ debug."""

    def __init__(
        self,
        estimator: DepthEstimator,
        baseline: BaselineArtifact,
        config: DetectionConfig,
        display: bool = True,
        log_interval: float = 2.0,
    ):
        """Khởi tạo detector và lưu các dependency chạy realtime."""
        if log_interval < 0:
            raise ValueError("log_interval không được âm.")
        self._estimator = estimator
        self._baseline = baseline
        self._detector = OccupancyDetector(baseline, config)
        self._display = display
        self._log_interval = log_interval

    # ─────────────────────────────────────────────────────────────────────────

    def run(self, source, **media_options) -> int:
        """Xử lý nguồn tới khi video kết thúc hoặc người dùng nhấn Q/Esc."""
        processed_frames = 0
        smooth_fps = 0.0
        run_started = time.perf_counter()
        last_time = run_started
        window_started = run_started
        window_frames = 0
        window_inference_time = 0.0
        window_detection_time = 0.0
        window_render_time = 0.0
        previous_state: OccupancyState | None = None
        LOGGER.info(
            "Bắt đầu detection full frame ở độ phân giải %dx%d.",
            self._baseline.frame_width,
            self._baseline.frame_height,
        )
        try:
            with MediaSources(source, **media_options) as media:
                for frames, _metas in media:
                    frame = resize_to_baseline(frames[0], self._baseline)

                    inference_started = time.perf_counter()
                    depth = self._estimator.predict(frame)
                    inference_time = time.perf_counter() - inference_started

                    detection_started = time.perf_counter()
                    output = self._detector.process(depth)
                    detection_time = time.perf_counter() - detection_started
                    processed_frames += 1

                    now = time.perf_counter()
                    instant_fps = 1.0 / max(now - last_time, 1e-6)
                    smooth_fps = (
                        instant_fps
                        if smooth_fps == 0.0
                        else 0.9 * smooth_fps + 0.1 * instant_fps
                    )
                    last_time = now
                    if output.result.state is not previous_state:
                        self._log_state(output)
                        previous_state = output.result.state

                    render_time = 0.0
                    should_stop = False
                    if self._display:
                        render_started = time.perf_counter()
                        should_stop = self._show(frame, output, smooth_fps)
                        render_time = time.perf_counter() - render_started

                    window_frames += 1
                    window_inference_time += inference_time
                    window_detection_time += detection_time
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
                            inference_time=window_inference_time,
                            detection_time=window_detection_time,
                            render_time=window_render_time,
                            state=output.result.state,
                        )
                        window_started = log_time
                        window_frames = 0
                        window_inference_time = 0.0
                        window_detection_time = 0.0
                        window_render_time = 0.0
                    if should_stop:
                        break
        finally:
            if self._display:
                cv2.destroyAllWindows()
        total_elapsed = max(time.perf_counter() - run_started, 1e-6)
        LOGGER.info(
            "Detection đã dừng sau %d frame | FPS trung bình=%.2f.",
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
        view = render_detection_view(frame, self._baseline, output, fps)
        cv2.imshow("Walkway detection", view)
        key = cv2.waitKey(1) & 0xFF
        return key in (27, ord("q"), ord("Q"))

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _log_state(output: DetectionOutput) -> None:
        """Ghi log khi trạng thái ổn định của lối đi thay đổi."""
        result = output.result
        LOGGER.info(
            "Trạng thái=%s | vùng lớn nhất=%.2f%% | ngoài ROI=%.2f%% | lý do=%s",
            result.state.value,
            result.largest_area_ratio * 100,
            result.outside_change_ratio * 100,
            result.reason or "-",
        )

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _log_performance(
        frames: int,
        elapsed: float,
        inference_time: float,
        detection_time: float,
        render_time: float,
        state: OccupancyState,
    ) -> None:
        """Ghi FPS và thời gian trung bình của từng công đoạn trong một cửa sổ đo."""
        frame_count = max(frames, 1)
        LOGGER.info(
            "FPS=%.2f | inference=%.1fms | detection=%.1fms | "
            "render=%.1fms | state=%s",
            frames / max(elapsed, 1e-6),
            inference_time * 1000 / frame_count,
            detection_time * 1000 / frame_count,
            render_time * 1000 / frame_count,
            state.value,
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
