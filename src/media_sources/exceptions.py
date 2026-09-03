class MediaSourceError(Exception):
    """Lỗi gốc của package media_sources."""


class StreamError(MediaSourceError):
    """Một stream reader (webcam/RTSP) gặp lỗi trong lúc đọc frame."""
