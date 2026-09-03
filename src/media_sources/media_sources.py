from __future__ import annotations

import numpy as np

from .factory import _is_sequence, create_media_source
from .models import SourceMeta

# ─────────────────────────────────────────────────────────────────────────────


class MediaSources:
    """Interface batch thống nhất để đọc frame từ nhiều nguồn media cùng loại.

    Wrapper mỏng quanh `create_media_source` — luôn trả batch `(frames, metas)`. Kết nối
    lazy: `__init__` chỉ dựng reader, chỉ mở khi vào `with`/lần `__next__` đầu tiên.

    kwargs được chuyển tiếp cho reader tương ứng (RtspReader: reconnect, reconnect_delay,
    max_reconnect_attempts, reconnect_forever, use_gstreamer, open_timeout_ms, read_timeout_ms).
    kwargs dư thừa bị lọc bỏ (log DEBUG).
    """

    def __init__(self, sources, **kwargs):
        # Luôn coi là batch: nguồn đơn cũng bọc thành list để giữ output (frames, metas).
        if not _is_sequence(sources):
            sources = [sources]
        self._reader = create_media_source(sources, **kwargs)

    def __iter__(self):
        return self

    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        return next(self._reader)

    def __enter__(self):
        self._reader.ensure_open()
        return self

    def __exit__(self, *args) -> None:
        self._reader.close()

    def release(self) -> None:
        """Giải phóng tất cả tài nguyên."""
        self._reader.close()
