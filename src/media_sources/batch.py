from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .exceptions import StreamError
from .models import SourceMeta
from .readers.base import BaseReader
from .utils import LOGGER

# ─────────────────────────────────────────────────────────────────────────────

# Thời gian chờ join thread khi đóng. RTSP read() có read_timeout ~5s nên thread có thể
# chưa thoát kịp; quá hạn thì bỏ qua (daemon thread sẽ được dọn khi tiến trình kết thúc) —
# mỗi thread tự release cap của mình ở finally để tránh race release-trong-khi-read().
_JOIN_TIMEOUT = 2.0


class _BaseBatch:
    """Base cho batch orchestrator: gói N reader đơn nguồn, trả batch (frames, metas).

    Batch luôn đồng nhất (mọi reader cùng loại) — factory đảm bảo điều này.
    """

    def __init__(self, readers: list[BaseReader]):
        if not readers:
            raise ValueError("Batch cần ít nhất một reader.")
        self._readers = readers
        self._opened = False

    # ─── vòng đời ──────────────────────────────────────────────────────────────

    def open(self) -> "_BaseBatch":
        """Mở tất cả reader con; nếu lỗi giữa chừng thì đóng các con đã mở rồi raise."""
        opened: list[BaseReader] = []
        try:
            for reader in self._readers:
                reader.open()
                opened.append(reader)
        except Exception:
            for reader in opened:
                reader.close()
            raise
        self._opened = True
        return self

    def close(self) -> None:
        for reader in self._readers:
            try:
                reader.close()
            except Exception as exc:
                LOGGER.warning("Không đóng được reader %s: %s", reader.source, exc)
        self._opened = False

    def ensure_open(self) -> None:
        if not self._opened:
            self.open()

    def release(self) -> None:
        """Alias của close() (tương thích API cũ)."""
        self.close()

    # ─── iterator / context manager ──────────────────────────────────────────

    def __iter__(self):
        return self

    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        raise NotImplementedError

    def __enter__(self) -> "_BaseBatch":
        self.ensure_open()
        return self

    def __exit__(self, *args) -> None:
        self.close()


# ─────────────────────────────────────────────────────────────────────────────


class SyncBatchReader(_BaseBatch):
    """Batch đọc đồng bộ (lockstep) cho nguồn tuần tự (image/video/youtube).

    Mỗi vòng đọc một frame từ MỌI reader song song (ThreadPoolExecutor), KHÔNG drop frame.
    Bất kỳ reader nào hết nguồn → kết thúc cả batch (StopIteration).
    """

    def __init__(self, readers: list[BaseReader]):
        super().__init__(readers)
        self._executor: ThreadPoolExecutor | None = None

    def open(self) -> "SyncBatchReader":
        super().open()
        self._executor = ThreadPoolExecutor(max_workers=max(len(self._readers), 1))
        return self

    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        self.ensure_open()
        results = list(self._executor.map(lambda r: r.read(), self._readers))

        if any(result is None for result in results):
            for reader, result in zip(self._readers, results):
                if result is None:
                    LOGGER.info("Nguồn kết thúc: %s", reader.source)
            self.close()
            raise StopIteration

        frames = [result[0] for result in results]
        metas = [result[1] for result in results]
        return frames, metas

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None
        super().close()


# ─────────────────────────────────────────────────────────────────────────────


class StreamBatchReader(_BaseBatch):
    """Batch đọc stream nền cho nguồn liên tục (rtsp/webcam).

    Mỗi reader một daemon thread đọc liên tục vào slot; `__next__` chỉ trả batch khi TẤT CẢ
    slot có frame mới hơn lần trả trước (đồng bộ theo index, luôn lấy frame mới nhất — drop
    frame cũ để giữ realtime). Reader hết nguồn → StopIteration; lỗi trong thread → StreamError.
    """

    def __init__(self, readers: list[BaseReader]):
        super().__init__(readers)
        n = len(readers)
        self._lock = threading.Condition()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._slots: list[tuple[np.ndarray, SourceMeta] | None] = [None] * n
        self._versions: list[int] = [0] * n
        self._last_seen: list[int] = [0] * n
        self._ended: list[bool] = [False] * n
        self._errors: list[BaseException | None] = [None] * n

    def open(self) -> "StreamBatchReader":
        super().open()  # mở tất cả reader con trước khi start thread
        n = len(self._readers)
        self._stop.clear()
        self._slots = [None] * n
        self._versions = [0] * n
        self._last_seen = [0] * n
        self._ended = [False] * n
        self._errors = [None] * n
        self._threads = []
        for i in range(n):
            t = threading.Thread(target=self._safe_loop, args=(i,), daemon=True, name=f"stream-reader-{i}")
            t.start()
            self._threads.append(t)
        return self

    # ─── thread loop ───────────────────────────────────────────────────────────

    def _safe_loop(self, i: int) -> None:
        reader = self._readers[i]
        try:
            while not self._stop.is_set():
                result = reader.read()
                if result is None:
                    self._mark_ended(i)
                    return
                frame, meta = result
                self._publish(i, frame, meta)
        except Exception as exc:
            LOGGER.error("Lỗi không xử lý được ở stream %d: %s", i, exc)
            self._mark_error(i, exc)
        finally:
            # Thread tự release cap của reader mình sở hữu (tránh race release-trong-khi-read).
            reader.close()

    def _publish(self, i: int, frame: np.ndarray, meta: SourceMeta) -> None:
        with self._lock:
            self._slots[i] = (frame, meta)
            self._versions[i] += 1
            self._lock.notify_all()

    def _mark_ended(self, i: int) -> None:
        with self._lock:
            self._ended[i] = True
            self._lock.notify_all()

    def _mark_error(self, i: int, exc: BaseException) -> None:
        with self._lock:
            self._errors[i] = exc
            self._lock.notify_all()

    # ─── iterator ──────────────────────────────────────────────────────────────

    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        self.ensure_open()
        n = len(self._readers)
        with self._lock:
            while True:
                if self._stop.is_set():
                    raise StopIteration

                # Stream lỗi → propagate cho consumer (không giấu thành StopIteration)
                for i, err in enumerate(self._errors):
                    if err is not None:
                        raise StreamError(f"Stream {i} gặp lỗi khi đọc frame: {err}") from err

                # Source đã kết thúc bình thường và không còn frame mới để yield
                for i in range(n):
                    if self._ended[i] and self._versions[i] <= self._last_seen[i]:
                        raise StopIteration

                # Tất cả slots đều có frame mới hơn lần trả trước
                if all(self._versions[i] > self._last_seen[i] for i in range(n)):
                    frames = [self._slots[i][0] for i in range(n)]
                    metas = [self._slots[i][1] for i in range(n)]
                    self._last_seen = list(self._versions)
                    return frames, metas

                self._lock.wait(timeout=0.1)

    # ─── đóng ──────────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._stop.set()
        # Tín hiệu cho các reader đang block (RTSP reconnect) thoát ra; KHÔNG release cap ở đây.
        for reader in self._readers:
            reader.request_stop()
        with self._lock:
            self._lock.notify_all()
        for t in self._threads:
            t.join(timeout=_JOIN_TIMEOUT)
            if t.is_alive():
                LOGGER.warning("Thread không dừng đúng hạn: %s", t.name)
        self._threads = []
        self._opened = False
