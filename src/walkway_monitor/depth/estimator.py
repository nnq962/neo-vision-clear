"""Interface depth estimator và adapter cho Depth Anything V2."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
import torch

from utils.logger import LOGGER


MODEL_CONFIGS = {
    "vits": {
        "encoder": "vits",
        "features": 64,
        "out_channels": [48, 96, 192, 384],
    },
    "vitb": {
        "encoder": "vitb",
        "features": 128,
        "out_channels": [96, 192, 384, 768],
    },
    "vitl": {
        "encoder": "vitl",
        "features": 256,
        "out_channels": [256, 512, 1024, 1024],
    },
}


class DepthEstimator(Protocol):
    """Giao diện tối thiểu của một model tạo relative depth map."""

    def predict(self, frame: np.ndarray) -> np.ndarray:
        """Suy luận một frame BGR và trả về depth map float32 cùng kích thước."""
        ...


class DepthAnythingEstimator:
    """Adapter tải checkpoint và chạy Depth Anything V2 trên thiết bị khả dụng."""

    def __init__(self, checkpoint: str | Path, encoder: str, input_size: int):
        """Khởi tạo model từ checkpoint với encoder và kích thước inference đã chọn."""
        if encoder not in MODEL_CONFIGS:
            raise ValueError(f"Encoder không được hỗ trợ: {encoder}")
        checkpoint_path = Path(checkpoint)
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy checkpoint: {checkpoint_path}")

        from depth_anything_v2.dpt import DepthAnythingV2

        self._input_size = input_size
        self._device = self._select_device()
        LOGGER.info("Đang tải Depth Anything %s trên %s...", encoder, self._device)
        model = DepthAnythingV2(**MODEL_CONFIGS[encoder])
        state_dict = torch.load(
            checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )
        model.load_state_dict(state_dict)
        self._model = model.to(self._device).eval()
        LOGGER.info("Đã tải checkpoint: %s", checkpoint_path)

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _select_device() -> str:
        """Chọn CUDA, MPS hoặc CPU theo khả năng của môi trường hiện tại."""
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    # ─────────────────────────────────────────────────────────────────────────

    def predict(self, frame: np.ndarray) -> np.ndarray:
        """Chạy Depth Anything và chuẩn hóa kết quả thành float32 hai chiều."""
        if not isinstance(frame, np.ndarray) or frame.ndim != 3:
            raise ValueError("Frame đầu vào phải là numpy.ndarray BGR ba chiều.")
        depth = self._model.infer_image(frame, self._input_size)
        depth = np.asarray(depth, dtype=np.float32)
        if depth.shape != frame.shape[:2]:
            raise RuntimeError("Depth Anything trả về depth map sai kích thước.")
        if not np.all(np.isfinite(depth)):
            raise RuntimeError("Depth Anything trả về giá trị không hữu hạn.")
        return depth
