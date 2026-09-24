from __future__ import annotations

from dataclasses import replace

import numpy as np
import yt_dlp

from ..models import SourceMeta, SourceType
from ..utils import LOGGER
from .video import VideoReader

# ─────────────────────────────────────────────────────────────────────────────


class YoutubeReader(VideoReader):
    """Đọc frame từ MỘT YouTube URL: dùng yt-dlp resolve direct stream URL rồi đọc như video.

    Giữ lockstep như VideoReader (is_stream=False ở cấp batch) — kể cả live stream cũng
    decode tuần tự. Metadata được patch lại theo thông tin yt-dlp (is_live, fps).
    """

    source_type = SourceType.YOUTUBE

    def __init__(self, source: str):
        super().__init__(source)
        self._youtube_url = str(source)
        self._name = self._youtube_url
        self._stream_url: str | None = None
        self._is_live = False
        self._yt_fps: float | None = None

    def _capture_target(self) -> str:
        return self._stream_url

    def open(self) -> "YoutubeReader":
        self._resolve()
        super().open()
        return self

    def _resolve(self) -> None:
        """Lấy direct stream URL + metadata từ yt-dlp."""
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
        }
        LOGGER.info("Đang lấy stream URL: %s", self._youtube_url)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self._youtube_url, download=False)
        except Exception as exc:
            LOGGER.error("Không lấy được stream URL: %s — %s", self._youtube_url, exc)
            raise RuntimeError(f"Không lấy được stream URL: {self._youtube_url}") from exc

        self._stream_url = info["url"]
        self._is_live = bool(info.get("is_live"))
        self._yt_fps = info.get("fps")
        w = info.get("width") or 0
        h = info.get("height") or 0
        LOGGER.info("  → YOUTUBE | %dx%d | %.0f fps | is_stream=%s | %s",
                    w, h, self._yt_fps or 0, self._is_live, info.get("title") or "(no title)")

    def _build_meta(self, frame: np.ndarray) -> SourceMeta:
        meta = super()._build_meta(frame)
        return replace(
            meta,
            name=self._youtube_url,
            source_type=SourceType.YOUTUBE,
            is_stream=self._is_live,
            # live stream không có tổng số frame xác định
            total_frames=None if self._is_live else meta.total_frames,
            # cap đôi khi đọc fps=0, fallback theo metadata yt-dlp
            fps=meta.fps if meta.fps and meta.fps > 0 else self._yt_fps,
        )
