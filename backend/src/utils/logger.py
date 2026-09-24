import os
import platform
import sys
import logging
import logging.config
import time
from datetime import datetime
import pytz

try:
    import colorlog
    COLORLOG_AVAILABLE = True
except ImportError:
    COLORLOG_AVAILABLE = False

LOGGING_NAME = "People Counter"


class DualTimezoneFormatter(logging.Formatter):
    """Formatter hiển thị cả UTC và VN time"""

    def converter(self, timestamp):
        return time.gmtime(timestamp)
    
    def format(self, record):
        # 1. Thêm VN time vào record
        utc_dt = datetime.fromtimestamp(record.created, tz=pytz.UTC)
        vn_dt = utc_dt.astimezone(pytz.timezone('Asia/Saigon'))
        record.vn_time = vn_dt.strftime('%H:%M:%S')
        
        # 2. TẠO mod_path TỪ ĐƯỜNG DẪN FILE
        try:
            # Lấy đường dẫn tương đối từ thư mục chạy code
            rel_path = os.path.relpath(record.pathname, os.getcwd())
            # Bỏ đuôi .py
            mod_path = os.path.splitext(rel_path)[0]
            # Đổi dấu slash chuẩn cho log (đề phòng chạy trên Windows)
            record.mod_path = mod_path.replace(os.sep, '/')
        except Exception:
            # Fallback về mặc định nếu lỗi
            record.mod_path = record.module

        return super().format(record)


class DualTimezoneColoredFormatter(colorlog.ColoredFormatter):
    """ColoredFormatter với dual timezone"""

    def converter(self, timestamp):
        return time.gmtime(timestamp)
    
    def format(self, record):
        # 1. Thêm VN time vào record
        utc_dt = datetime.fromtimestamp(record.created, tz=pytz.UTC)
        vn_dt = utc_dt.astimezone(pytz.timezone('Asia/Saigon'))
        record.vn_time = vn_dt.strftime('%H:%M:%S')
        
        # 2. TẠO mod_path TỪ ĐƯỜNG DẪN FILE (Copy giống hệt class trên)
        try:
            rel_path = os.path.relpath(record.pathname, os.getcwd())
            mod_path = os.path.splitext(rel_path)[0]
            record.mod_path = mod_path.replace(os.sep, '/')
        except Exception:
            record.mod_path = record.module

        return super().format(record)


def set_logging(name=LOGGING_NAME, verbose=True, debug=False):
    level = logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    formatter_str = "%(vn_time)s | %(levelname)s | %(mod_path)s:%(lineno)d | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Formatters
    formatters = {
        name: {
            "()": DualTimezoneFormatter,
            "format": formatter_str,
            "datefmt": datefmt
        }
    }

    # Chỉ dùng color khi output là terminal (không phải file)
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
            }
        }

    # Handlers: INFO/WARNING/DEBUG -> stdout, ERROR/CRITICAL -> stderr
    handlers = {
        "console_out": {
            "class": "logging.StreamHandler",
            "level": logging.DEBUG,
            "formatter": "color" if use_color else name,
            "stream": "ext://sys.stdout",
            "filters": ["info_and_below"]  # Chỉ INFO, WARNING, DEBUG
        },
        "console_err": {
            "class": "logging.StreamHandler",
            "level": logging.ERROR,  # ERROR và CRITICAL
            "formatter": "color" if use_color else name,
            "stream": "ext://sys.stderr"
        }
    }

    # Filter để chỉ cho phép INFO, WARNING, DEBUG qua stdout
    class InfoAndBelowFilter(logging.Filter):
        def filter(self, record):
            return record.levelno < logging.ERROR  # < ERROR nghĩa là DEBUG, INFO, WARNING

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "filters": {
            "info_and_below": {
                "()": InfoAndBelowFilter
            }
        },
        "handlers": handlers,
        "loggers": {
            name: {
                "handlers": ["console_out", "console_err"],  # Dùng CẢ 2 handlers
                "level": level,
                "propagate": False
            }
        }
    })

    # Emoji safe logging cho Windows
    logger = logging.getLogger(name)
    if platform.system() == 'Windows':
        for fn in logger.info, logger.warning:
            setattr(logger, fn.__name__, lambda x: fn(str(x)))


def restore_level_names():
    logging.addLevelName(10, 'DEBUG')
    logging.addLevelName(20, 'INFO')
    logging.addLevelName(30, 'WARNING')
    logging.addLevelName(40, 'ERROR')
    logging.addLevelName(50, 'CRITICAL')


# Gọi khởi tạo logger
set_logging(debug=True)
LOGGER = logging.getLogger(LOGGING_NAME)
# refresh
