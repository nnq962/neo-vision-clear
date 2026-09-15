"""Tiện ích giải phóng bộ nhớ dùng chung cho các worker model."""

from __future__ import annotations

import gc

import torch

from utils.logger import LOGGER


# ─────────────────────────────────────────────────────────────────────────────


def release_worker_memory(worker_name: str) -> None:
    """Thu gom object và trả CUDA cache sau khi một worker kết thúc."""
    # Bước 1: giải phóng các vòng tham chiếu Python sau khi worker bỏ model.
    gc.collect()

    # Bước 2: CPU-only không cần gọi API CUDA; lỗi cleanup không được giết server.
    if not torch.cuda.is_available():
        return
    try:
        torch.cuda.empty_cache()
    except Exception:
        LOGGER.warning(
            "Không thể giải phóng CUDA cache của %s.",
            worker_name,
            exc_info=True,
        )
