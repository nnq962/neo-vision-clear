"""Interface depth estimator và adapter cho Depth Anything V2."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

import numpy as np
import torch

from utils.logger import LOGGER
from walkway_monitor.config import SUPPORTED_ENCODERS


MODEL_CONFIGS: dict[str, dict[str, object]] = {
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

if set(MODEL_CONFIGS) != set(SUPPORTED_ENCODERS):
    raise RuntimeError("Cấu hình model không khớp danh sách encoder hỗ trợ.")


class DepthEstimator(Protocol):
    """Giao diện model tạo relative depth map đơn lẻ hoặc theo batch."""

    def predict(self, frame: np.ndarray) -> np.ndarray:
        """Suy luận một frame BGR và trả về depth map float32 cùng kích thước."""
        ...

    def predict_batch(self, frames: Sequence[np.ndarray]) -> list[np.ndarray]:
        """Suy luận một batch frame BGR và trả depth map theo đúng thứ tự."""
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
        return self.predict_batch([frame])[0]

    # ─────────────────────────────────────────────────────────────────────────

    def predict_batch(self, frames: Sequence[np.ndarray]) -> list[np.ndarray]:
        """Chạy một forward cho nhiều frame và kiểm tra từng depth map đầu ra."""
        normalized_frames = list(frames)
        if not normalized_frames:
            raise ValueError("Batch frame không được rỗng.")
        for frame in normalized_frames:
            if not isinstance(frame, np.ndarray) or frame.ndim != 3:
                raise ValueError("Mỗi frame phải là numpy.ndarray BGR ba chiều.")

        # Bước 1: gom preprocessing và forward vào implementation model để chỉ
        # chuyển một tensor batch qua accelerator.
        depths = self._model.infer_image_batch(
            normalized_frames,
            self._input_size,
        )
        if len(depths) != len(normalized_frames):
            raise RuntimeError("Depth Anything trả về sai số lượng depth map.")

        # Bước 2: chuẩn hóa dtype và xác nhận từng output khớp frame tương ứng.
        normalized_depths: list[np.ndarray] = []
        for frame, depth in zip(normalized_frames, depths):
            normalized_depth = np.asarray(depth, dtype=np.float32)
            if normalized_depth.shape != frame.shape[:2]:
                raise RuntimeError("Depth Anything trả về depth map sai kích thước.")
            if not np.all(np.isfinite(normalized_depth)):
                raise RuntimeError("Depth Anything trả về giá trị không hữu hạn.")
            normalized_depths.append(normalized_depth)
        return normalized_depths


# ─────────────────────────────────────────────────────────────────────────────


def predict_depth_batch(
    estimator: DepthEstimator,
    frames: Sequence[np.ndarray],
) -> list[np.ndarray]:
    """Gọi API batch của estimator và kiểm tra số lượng depth map."""
    normalized_frames = list(frames)
    if not normalized_frames:
        raise ValueError("Batch frame không được rỗng.")

    # Bước 1: mọi estimator phải xử lý batch bằng một lời gọi thống nhất.
    depths = list(estimator.predict_batch(normalized_frames))
    if len(depths) != len(normalized_frames):
        raise RuntimeError("Estimator trả về sai số lượng depth map trong batch.")
    return depths
