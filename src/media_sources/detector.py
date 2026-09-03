from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from .models import SourceType


_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
_VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".m4v"}
_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "youtu.be", "www.youtu.be",
    "youtube-nocookie.com", "www.youtube-nocookie.com",
}


def _is_youtube(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in _YOUTUBE_HOSTS or host.endswith(".youtube.com")


def _classify_one(item) -> SourceType:
    """Phân loại một nguồn media đơn lẻ thành SourceType."""
    if isinstance(item, int):
        return SourceType.WEBCAM

    if isinstance(item, np.ndarray):
        return SourceType.IMAGE

    if isinstance(item, (str, Path)):
        s = str(item)
        if s.lower().startswith(("rtsp://", "rtmp://")):
            return SourceType.RTSP
        if _is_youtube(s):
            return SourceType.YOUTUBE
        ext = Path(s).suffix.lower()
        if ext in _IMAGE_EXT:
            return SourceType.IMAGE
        if ext in _VIDEO_EXT:
            return SourceType.VIDEO

    raise ValueError(f"Không nhận diện được loại nguồn: {type(item).__name__} — {item!r}")


def detect_source_type(sources: list) -> SourceType:
    """Phân loại mọi item và đảm bảo cả batch cùng một loại nguồn.

    Raise ValueError nếu danh sách rỗng hoặc batch trộn nhiều loại — batch luôn phải đồng nhất.
    """
    if not sources:
        raise ValueError("Danh sách sources không được rỗng.")

    types = [_classify_one(item) for item in sources]
    unique = set(types)
    if len(unique) > 1:
        chi_tiet = ", ".join(f"{_label(src)}→{t.name}" for src, t in zip(sources, types))
        raise ValueError(
            f"Batch phải cùng một loại nguồn, nhưng nhận được nhiều loại: {chi_tiet}"
        )

    return types[0]


def _label(src) -> str:
    """Nhãn gọn cho thông báo lỗi (tránh in cả nội dung ndarray)."""
    if isinstance(src, np.ndarray):
        return f"<ndarray {src.shape}>"
    return repr(src)
