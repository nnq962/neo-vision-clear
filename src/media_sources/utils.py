import logging
import logging.config
import os
import platform
import sys
from datetime import datetime

import cv2
import numpy as np
import pytz

try:
    import colorlog
    COLORLOG_AVAILABLE = True
except ImportError:
    COLORLOG_AVAILABLE = False

LOGGING_NAME = "media_sources"

# ─────────────────────────────────────────────────────────────────────────────


class DualTimezoneFormatter(logging.Formatter):
    """Formatter hiển thị giờ VN (Asia/Saigon) và đường dẫn file tương đối."""
    converter = lambda *args: __import__('time').gmtime(args[1])

    def format(self, record):
        utc_dt = datetime.fromtimestamp(record.created, tz=pytz.UTC)
        vn_dt = utc_dt.astimezone(pytz.timezone('Asia/Saigon'))
        record.vn_time = vn_dt.strftime('%H:%M:%S')
        try:
            rel_path = os.path.relpath(record.pathname, os.getcwd())
            record.mod_path = os.path.splitext(rel_path)[0].replace(os.sep, '/')
        except Exception:
            record.mod_path = record.module
        return super().format(record)


# ─────────────────────────────────────────────────────────────────────────────

# Chỉ định nghĩa khi có colorlog — nếu không sẽ NameError lúc import (colorlog là optional).
if COLORLOG_AVAILABLE:

    class DualTimezoneColoredFormatter(colorlog.ColoredFormatter):
        """ColoredFormatter với giờ VN và đường dẫn file tương đối."""
        converter = lambda *args: __import__('time').gmtime(args[1])

        def format(self, record):
            utc_dt = datetime.fromtimestamp(record.created, tz=pytz.UTC)
            vn_dt = utc_dt.astimezone(pytz.timezone('Asia/Saigon'))
            record.vn_time = vn_dt.strftime('%H:%M:%S')
            try:
                rel_path = os.path.relpath(record.pathname, os.getcwd())
                record.mod_path = os.path.splitext(rel_path)[0].replace(os.sep, '/')
            except Exception:
                record.mod_path = record.module
            return super().format(record)


# ─────────────────────────────────────────────────────────────────────────────


def set_logging(name: str = LOGGING_NAME, verbose: bool = True, debug: bool = False) -> None:
    """Cấu hình logger: INFO/DEBUG/WARNING → stdout, ERROR/CRITICAL → stderr."""
    level = logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    formatter_str = "%(vn_time)s | %(levelname)s | %(mod_path)s:%(lineno)d | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    formatters: dict = {
        name: {
            "()": DualTimezoneFormatter,
            "format": formatter_str,
            "datefmt": datefmt,
        }
    }

    use_color = COLORLOG_AVAILABLE and sys.stdout.isatty()
    if use_color:
        formatters["color"] = {
            "()": DualTimezoneColoredFormatter,
            "format": "%(log_color)s" + formatter_str,
            "datefmt": datefmt,
            "log_colors": {
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        }

    class InfoAndBelowFilter(logging.Filter):
        def filter(self, record):
            return record.levelno < logging.ERROR

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "filters": {"info_and_below": {"()": InfoAndBelowFilter}},
        "handlers": {
            "console_out": {
                "class": "logging.StreamHandler",
                "level": logging.DEBUG,
                "formatter": "color" if use_color else name,
                "stream": "ext://sys.stdout",
                "filters": ["info_and_below"],
            },
            "console_err": {
                "class": "logging.StreamHandler",
                "level": logging.ERROR,
                "formatter": "color" if use_color else name,
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            name: {
                "handlers": ["console_out", "console_err"],
                "level": level,
                "propagate": False,
            }
        },
    })

    logger = logging.getLogger(name)
    if platform.system() == "Windows":
        for fn in (logger.info, logger.warning):
            setattr(logger, fn.__name__, lambda x: fn(str(x)))


def restore_level_names() -> None:
    logging.addLevelName(10, "DEBUG")
    logging.addLevelName(20, "INFO")
    logging.addLevelName(30, "WARNING")
    logging.addLevelName(40, "ERROR")
    logging.addLevelName(50, "CRITICAL")


# Library-safe: không tự cấu hình logging khi import. App gọi set_logging() để bật log màu.
LOGGER = logging.getLogger(LOGGING_NAME)
LOGGER.addHandler(logging.NullHandler())

# ─────────────────────────────────────────────────────────────────────────────


def ensure_bgr(frame: np.ndarray) -> np.ndarray:
    """Chuẩn hóa frame về 3-channel BGR; reject shape/channel không hợp lệ.

    Cho phép: grayscale (H,W) hoặc (H,W,1), BGR (H,W,3), BGRA (H,W,4).
    Reject: không phải ndarray, ndim ∉ {2,3}, hoặc channel ∉ {1,3,4}.
    """
    if not isinstance(frame, np.ndarray):
        raise TypeError(f"Frame phải là numpy.ndarray, nhận {type(frame).__name__}.")

    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    if frame.ndim != 3:
        raise ValueError(f"Frame phải có 2 hoặc 3 chiều, nhận shape {frame.shape}.")

    channels = frame.shape[2]
    if channels == 1:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if channels == 3:
        return frame
    if channels == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    raise ValueError(f"Frame phải có 1, 3 hoặc 4 channel, nhận {channels}.")


# ─────────────────────────────────────────────────────────────────────────────


def open_capture(
    src,
    backend: int = cv2.CAP_ANY,
    open_timeout_ms: int | None = None,
    read_timeout_ms: int | None = None,
) -> cv2.VideoCapture:
    """Tạo cv2.VideoCapture có open/read timeout để chống treo vô hạn khi nguồn lỗi.

    Dùng overload params của OpenCV; build không hỗ trợ thì fallback constructor thường.
    Lưu ý: nhiều backend webcam (USB) có thể bỏ qua timeout — đây là best-effort.
    """
    params: list[int] = []
    if open_timeout_ms is not None and hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
        params += [int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC), int(open_timeout_ms)]
    if read_timeout_ms is not None and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
        params += [int(cv2.CAP_PROP_READ_TIMEOUT_MSEC), int(read_timeout_ms)]
    if params:
        try:
            return cv2.VideoCapture(src, backend, params)
        except (TypeError, cv2.error):
            pass  # build OpenCV không hỗ trợ overload params → fallback
    return cv2.VideoCapture(src, backend)
