from __future__ import annotations

import platform
from pathlib import Path
import threading
import time

import cv2
import numpy as np

from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr, open_capture
from .base import BaseReader

# ─────────────────────────────────────────────────────────────────────────────


class RtspReader(BaseReader):
    """Đọc frame từ MỘT RTSP/RTMP stream với GStreamer/FFMPEG backend và auto-reconnect.

    Reconnect nằm bên trong `read()`: khi đọc thất bại, reader tự thử lại (exponential
    backoff) cho tới khi có frame hoặc bị `close()`. Thread điều phối ở StreamBatchReader
    chỉ việc gọi `read()` lặp lại; `close()` set stop-event để `read()` đang reconnect thoát ra.
    """

    source_type = SourceType.RTSP
    is_stream = True

    # Chỉ cảnh báo "OpenCV không có GStreamer" một lần cho cả tiến trình.
    _gstreamer_warning_emitted = False

    def __init__(
        self,
        source: str,
        *,
        reconnect: bool = True,
        reconnect_delay: float = 2.0,
        max_reconnect_attempts: int = 5,
        reconnect_forever: bool = True,
        use_gstreamer: bool = True,
        jetson_hardware_decode: bool = True,
        gstreamer_latency_ms: int = 0,
        open_timeout_ms: int = 5000,
        read_timeout_ms: int = 5000,
    ):
        """Lưu cấu hình RTSP và lựa chọn decoder phần cứng phù hợp nền tảng."""
        if gstreamer_latency_ms < 0:
            raise ValueError("gstreamer_latency_ms không được là số âm.")
        super().__init__(source)
        self._reconnect = reconnect
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_forever = reconnect_forever
        self._use_gstreamer = use_gstreamer
        self._jetson_hardware_decode = (
            jetson_hardware_decode and self._is_jetson_platform()
        )
        self._gstreamer_latency_ms = gstreamer_latency_ms
        self._open_timeout_ms = open_timeout_ms
        self._read_timeout_ms = read_timeout_ms
        self._cap: cv2.VideoCapture | None = None
        self._backend = "unknown"
        self._fps = 0.0
        self._stop_reconnect = threading.Event()

    # ─── vòng đời ──────────────────────────────────────────────────────────────

    def open(self) -> "RtspReader":
        """Mở stream và ghi nhận backend, độ phân giải cùng FPS thực tế."""
        url = self._source
        if (
            self._use_gstreamer
            and not self._opencv_has_gstreamer()
            and not RtspReader._gstreamer_warning_emitted
        ):
            LOGGER.warning(
                "use_gstreamer=True nhưng OpenCV không được build với GStreamer; "
                "tất cả stream sẽ dùng FFMPEG."
            )
            RtspReader._gstreamer_warning_emitted = True
        elif self._use_gstreamer and self._jetson_hardware_decode:
            LOGGER.info("Ưu tiên GStreamer hardware decode của Jetson.")

        self._stop_reconnect.clear()
        LOGGER.info("Đang kết nối stream: %s", url)
        cap, backend = self._open_cap(url)
        self._cap = cap
        self._backend = backend
        self._fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        res = f"{w}x{h}" if w > 0 and h > 0 else "unknown"
        fps_str = f"{self._fps:.1f} fps" if self._fps > 0 else "fps=unknown"
        LOGGER.info(
            "  → RTSP | %s | %s | backend=%s | is_stream=True",
            res,
            fps_str,
            backend,
        )
        self._opened = True
        self._frame_index = 0
        return self

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        """Đọc frame mới nhất và gắn metadata của nguồn RTSP."""
        self.ensure_open()
        frame = self._read_raw_frame()
        if frame is None:
            return None

        frame = ensure_bgr(frame)
        h, w = frame.shape[:2]
        meta = SourceMeta(
            name=self._source,
            source_type=SourceType.RTSP,
            frame_index=self._frame_index,
            resolution=(w, h),
            fps=self._fps,
            is_stream=True,
            timestamp=time.time(),
        )
        self._frame_index += 1
        return frame, meta

    def request_stop(self) -> None:
        """Yêu cầu vòng đọc hoặc reconnect đang chờ dừng sớm."""
        # Cho phép batch dừng vòng reconnect/đọc mà không release cap (thread tự release ở close()).
        self._stop_reconnect.set()

    def close(self) -> None:
        """Dừng reconnect và giải phóng VideoCapture hiện tại."""
        self._stop_reconnect.set()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._opened = False

    # ─── đọc + reconnect ───────────────────────────────────────────────────────

    def _read_raw_frame(self) -> np.ndarray | None:
        """Đọc 1 frame thô; nếu thất bại thì áp dụng chính sách reconnect."""
        image = self._read_capture_once()
        if image is not None:
            return image

        if not self._reconnect:
            LOGGER.warning("RTSP mất kết nối, không reconnect: %s", self._source)
            return None

        return self._reconnect_and_read()

    def _read_capture_once(self) -> np.ndarray | None:
        """Đọc 1 frame từ cap hiện tại, không reconnect."""
        if self._stop_reconnect.is_set() or self._cap is None:
            return None
        ok, image = self._cap.read()
        if ok and image is not None:
            return image
        return None

    def _reconnect_and_read(self) -> np.ndarray | None:
        """Thử reconnect (exponential backoff) tới khi có frame, bị close, hoặc hết lượt."""
        attempt = 0
        while not self._stop_reconnect.is_set():
            attempt += 1
            if not self._reconnect_forever and attempt > self._max_reconnect_attempts:
                LOGGER.error(
                    "RTSP bỏ cuộc sau %d lần reconnect: %s",
                    self._max_reconnect_attempts,
                    self._source,
                )
                return None

            LOGGER.warning(
                "RTSP mất kết nối, thử lại lần %d: %s",
                attempt,
                self._source,
            )
            if self._cap is not None:
                self._cap.release()
                self._cap = None

            # Backoff: tăng delay theo số lần thất bại, tối đa 60s
            delay = min(self._reconnect_delay * (2 ** min(attempt - 1, 5)), 60.0)
            if self._stop_reconnect.wait(timeout=delay):
                return None

            try:
                cap, backend = self._open_cap(self._source)
                self._cap = cap
                self._backend = backend
                self._fps = cap.get(cv2.CAP_PROP_FPS)
                LOGGER.info(
                    "RTSP reconnect thành công (lần %d, backend=%s): %s",
                    attempt,
                    backend,
                    self._source,
                )
                image = self._read_capture_once()
                if image is not None:
                    return image
            except Exception as exc:
                LOGGER.warning("RTSP reconnect lần %d thất bại: %s", attempt, exc)
                self._cap = None

        return None

    # ─── mở kết nối ──────────────────────────────────────────────────────────

    def _open_cap(self, url: str) -> tuple[cv2.VideoCapture, str]:
        """Thử GStreamer trước, fallback sang FFMPEG. Trả về (cap, backend_label).

        RTMP bỏ qua GStreamer (rtspsrc không hỗ trợ rtmp://).
        """
        is_rtmp = url.lower().startswith("rtmp://")
        if self._use_gstreamer and not is_rtmp and self._opencv_has_gstreamer():
            result = self._open_gstreamer(url)
            if result is not None:
                return result
            LOGGER.warning(
                "GStreamer pipeline không thành công, fallback sang FFMPEG: %s",
                url,
            )
        return self._open_ffmpeg(url)

    def _open_ffmpeg(self, url: str) -> tuple[cv2.VideoCapture, str]:
        cap = open_capture(
            url,
            cv2.CAP_FFMPEG,
            self._open_timeout_ms,
            self._read_timeout_ms,
        )
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"Không kết nối được stream: {url}")
        return cap, "FFMPEG"

    def _open_gstreamer(self, url: str) -> tuple[cv2.VideoCapture, str] | None:
        """Thử lần lượt h264 → h265; warm-up với timeout ngắn để detect codec nhanh.

        Dùng _WARMUP_TIMEOUT_MS thay vì None để tránh block vô hạn khi codec sai
        (GStreamer không có frame → pull_sample() block đến internal TCP timeout ~30s).
        Sau khi confirm frame thì apply production read_timeout_ms.
        """
        # Decoder phần cứng Jetson có thể cần vài giây để nạp plugin và
        # chờ keyframe đầu tiên. Timeout 500ms khiến OpenCV gọi retrieve
        # lúc GstSample chưa có và spam cảnh báo gst_sample_get_caps().
        _WARMUP_TIMEOUT_MS = 5000
        _WARMUP_ATTEMPTS = 2  # giữ tổng thời gian dò mỗi codec tối đa 10s
        for codec in ("h264", "h265"):
            cap = open_capture(
                self._build_gstreamer_pipeline(url, codec),
                cv2.CAP_GSTREAMER,
                self._open_timeout_ms,
                _WARMUP_TIMEOUT_MS,
            )
            if not cap.isOpened():
                cap.release()
                continue
            for _ in range(_WARMUP_ATTEMPTS):
                ok, frame = cap.read()
                if ok and frame is not None:
                    if self._read_timeout_ms is not None and hasattr(
                        cv2,
                        "CAP_PROP_READ_TIMEOUT_MSEC",
                    ):
                        cap.set(
                            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                            float(self._read_timeout_ms),
                        )
                    decoder = "Jetson" if self._jetson_hardware_decode else "Software"
                    return cap, f"GStreamer/{decoder}/{codec}"
            cap.release()
        return None

    def _build_gstreamer_pipeline(self, url: str, codec: str) -> str:
        """Dựng pipeline low-latency dùng decoder Jetson hoặc decoder CPU."""
        url_esc = url.replace('"', '\\"')
        depay_and_parse = (
            "rtph265depay ! h265parse"
            if codec == "h265"
            else "rtph264depay ! h264parse"
        )
        if self._jetson_hardware_decode:
            # Decoder giữ frame trong NVMM; nvvidconv chỉ tải về system memory
            # ở BGRx trước bước chuyển BGR bắt buộc cho numpy/OpenCV.
            decode_and_convert = (
                f"{depay_and_parse} "
                "! nvv4l2decoder enable-max-performance=1 "
                "! nvvidconv ! video/x-raw,format=BGRx "
                "! videoconvert"
            )
        else:
            software_decoder = "avdec_h265" if codec == "h265" else "avdec_h264"
            decode_and_convert = (
                f"{depay_and_parse} ! {software_decoder} ! videoconvert"
            )
        return (
            f'rtspsrc location="{url_esc}" protocols=tcp '
            f"latency={self._gstreamer_latency_ms} "
            f"drop-on-latency=true do-retransmission=false "
            f"! {decode_and_convert} ! video/x-raw,format=BGR "
            f"! queue leaky=downstream max-size-buffers=1 "
            f"max-size-bytes=0 max-size-time=0 "
            f"! appsink sync=false async=false drop=true max-buffers=1"
        )

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_jetson_platform() -> bool:
        """Nhận diện Jetson bằng kiến trúc ARM64 và marker/plugin của JetPack."""
        # Bước 1: không thử plugin NVIDIA trên máy không phải ARM64.
        if platform.machine().lower() not in {"aarch64", "arm64"}:
            return False

        # Bước 2: ưu tiên marker JetPack, sau đó nhận diện hai plugin bắt buộc.
        if Path("/etc/nv_tegra_release").is_file():
            return True
        plugin_directory = Path("/usr/lib/aarch64-linux-gnu/gstreamer-1.0")
        return (
            (plugin_directory / "libgstnvvideo4linux2.so").is_file()
            and (plugin_directory / "libgstnvvidconv.so").is_file()
        )

    @staticmethod
    def _opencv_has_gstreamer() -> bool:
        """Trả True khi OpenCV hiện tại được liên kết với GStreamer."""
        return any(
            "GStreamer:" in line and "YES" in line
            for line in cv2.getBuildInformation().splitlines()
        )
