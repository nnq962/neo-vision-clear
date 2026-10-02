"""Adapter TensorRT cho Depth Anything V2 với batch tĩnh hoặc động."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
import torch.nn.functional as F

from depth_anything_v2.dpt import prepare_image
from utils.logger import LOGGER


def read_engine_metadata(
    engine_path: str | Path,
    encoder: str,
    input_size: int,
    checkpoint: str | Path | None = None,
) -> dict:
    """Kiểm tra manifest để tránh chạy nhầm engine với baseline hiện tại."""
    path = Path(engine_path)
    metadata_path = Path(f"{path}.json")
    if not path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError(
            f"Thiếu TensorRT engine hoặc manifest: {path}, {metadata_path}"
        )
    with metadata_path.open(encoding="utf-8") as source:
        metadata = json.load(source)
    if metadata.get("schema_version") not in (1, 2):
        raise ValueError("Schema manifest TensorRT không được hỗ trợ.")
    if metadata.get("encoder") != encoder or metadata.get("input_size") != input_size:
        raise ValueError("Engine TensorRT không khớp encoder hoặc input_size của baseline.")
    if metadata.get("precision") != "fp16":
        raise ValueError("Manifest TensorRT phải khai báo precision=fp16.")
    if metadata["schema_version"] == 2 and (
        metadata.get("min_batch") != 1 or metadata.get("max_batch") != 2
    ):
        raise ValueError("Engine TensorRT batch động phải hỗ trợ batch 1–2.")
    if checkpoint is not None:
        digest = hashlib.sha256()
        with Path(checkpoint).open("rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        if digest.hexdigest() != metadata.get("checkpoint_sha256"):
            raise ValueError("Engine TensorRT được build từ checkpoint khác.")
    return metadata


# ─────────────────────────────────────────────────────────────────────────────


def dynamic_engine_path(
    directory: str | Path,
    encoder: str,
    input_size: int,
    frame_width: int,
    frame_height: int,
) -> Path:
    """Tìm engine batch 1–2 theo shape do chính preprocessing tạo ra."""
    # Bước 1: dùng cùng transform với inference để tránh đoán chiều ngang.
    frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
    image, _size = prepare_image(frame, input_size)
    height, width = image.shape[1:]
    return Path(directory) / f"{encoder}-b1-2-{height}x{width}.engine"


class TensorRTDepthEstimator:
    """Chạy engine TensorRT bằng bộ nhớ và CUDA stream của PyTorch."""

    # ─────────────────────────────────────────────────────────────────────────

    def __init__(
        self,
        engine_path: str | Path,
        encoder: str,
        input_size: int,
        checkpoint: str | Path | None = None,
    ):
        """Nạp engine đã build cho đúng encoder, input size và profile batch."""
        path = Path(engine_path)
        metadata = read_engine_metadata(path, encoder, input_size, checkpoint)
        if not torch.cuda.is_available():
            raise RuntimeError("TensorRT cần CUDA trên Jetson.")
        try:
            import tensorrt as trt
        except ImportError as exc:
            raise RuntimeError(
                "Không tìm thấy Python binding TensorRT trong môi trường backend."
            ) from exc

        self._logger = trt.Logger(trt.Logger.WARNING)
        self._runtime = trt.Runtime(self._logger)
        self._engine = self._runtime.deserialize_cuda_engine(path.read_bytes())
        if self._engine is None:
            raise RuntimeError(f"Không thể nạp TensorRT engine: {path}")
        if self._engine.num_bindings != 2:
            raise ValueError("Engine TensorRT phải có đúng một input và một output.")
        self._input_index = self._engine.get_binding_index("input")
        self._output_index = self._engine.get_binding_index("depth")
        if self._input_index < 0 or self._output_index < 0:
            raise ValueError("Engine TensorRT cần binding 'input' và 'depth'.")
        if not self._engine.binding_is_input(self._input_index):
            raise ValueError("Binding 'input' của TensorRT không phải input.")
        self._input_shape = tuple(self._engine.get_binding_shape(self._input_index))
        self._output_shape = tuple(self._engine.get_binding_shape(self._output_index))
        if list(self._input_shape) != metadata.get("input_shape"):
            raise ValueError("Shape engine TensorRT khác manifest.")
        if self._output_shape != (
            self._input_shape[0], self._input_shape[2], self._input_shape[3]
        ):
            raise ValueError("Output TensorRT không khớp shape depth dự kiến.")
        self._dynamic_batch = self._input_shape[0] == -1
        if self._dynamic_batch:
            if metadata["schema_version"] != 2:
                raise ValueError("Engine batch động cần manifest schema 2.")
            minimum, _optimal, maximum = self._engine.get_profile_shape(
                0, self._input_index
            )
            if minimum != (1,) + self._input_shape[1:] or maximum != (
                2,
            ) + self._input_shape[1:]:
                raise ValueError("Profile engine TensorRT phải hỗ trợ batch 1–2.")
        elif metadata["schema_version"] != 1:
            raise ValueError("Engine batch tĩnh cần manifest schema 1.")
        if self._engine.get_binding_dtype(self._input_index) != trt.float32:
            raise ValueError("Engine TensorRT cần input float32.")
        output_dtype = self._engine.get_binding_dtype(self._output_index)
        if output_dtype not in (trt.float32, trt.float16):
            raise ValueError("Engine TensorRT cần output float32 hoặc float16.")
        self._output_torch_dtype = (
            torch.float32 if output_dtype == trt.float32 else torch.float16
        )
        self._context = self._engine.create_execution_context()
        if self._context is None:
            raise RuntimeError("Không thể tạo TensorRT execution context.")
        self._input_size = input_size
        LOGGER.info("Đã tải TensorRT engine %s, shape=%s.", path, self._input_shape)

    # ─────────────────────────────────────────────────────────────────────────

    def predict(self, frame: np.ndarray) -> np.ndarray:
        """Suy luận một frame và trả depth cùng kích thước frame."""
        return self.predict_batch([frame])[0]

    # ─────────────────────────────────────────────────────────────────────────

    def predict_batch(self, frames: Sequence[np.ndarray]) -> list[np.ndarray]:
        """Suy luận batch 1–2 hoặc batch tĩnh và resize depth về từng frame."""
        normalized_frames = list(frames)
        if not normalized_frames:
            raise ValueError("Batch frame không được rỗng.")
        for frame in normalized_frames:
            if not isinstance(frame, np.ndarray) or frame.ndim != 3:
                raise ValueError("Mỗi frame phải là numpy.ndarray BGR ba chiều.")

        # Bước 1: dùng chính phép tiền xử lý của PyTorch để giữ cùng chuẩn ảnh.
        prepared = [prepare_image(frame, self._input_size) for frame in normalized_frames]
        tensors = [item[0] for item in prepared]
        sizes = [item[1] for item in prepared]
        actual_shape = (len(tensors),) + tuple(tensors[0].shape)
        expected_spatial = self._input_shape[1:]
        valid_batch = (
            1 <= len(tensors) <= 2
            if self._dynamic_batch
            else len(tensors) == self._input_shape[0]
        )
        if not valid_batch or actual_shape[1:] != expected_spatial or any(
            tensor.shape != tensors[0].shape for tensor in tensors[1:]
        ):
            raise ValueError(
                f"Engine TensorRT cần input {self._input_shape}, nhận {actual_shape}."
            )

        # Bước 2: Torch cấp phát CUDA buffer và TensorRT chạy trên cùng stream.
        with torch.no_grad():
            inputs = torch.stack(tensors).to(device="cuda")
            if self._dynamic_batch and not self._context.set_binding_shape(
                self._input_index, actual_shape
            ):
                raise RuntimeError(f"TensorRT không nhận shape {actual_shape}.")
            output_shape = (
                tuple(self._context.get_binding_shape(self._output_index))
                if self._dynamic_batch
                else self._output_shape
            )
            if output_shape != (len(tensors), *actual_shape[2:]):
                raise RuntimeError("TensorRT trả về output shape không hợp lệ.")
            outputs = torch.empty(
                output_shape,
                dtype=self._output_torch_dtype,
                device="cuda",
            )
            bindings = [0] * self._engine.num_bindings
            bindings[self._input_index] = inputs.data_ptr()
            bindings[self._output_index] = outputs.data_ptr()
            stream = torch.cuda.current_stream()
            if not self._context.execute_async_v2(bindings, stream.cuda_stream):
                raise RuntimeError("TensorRT không thực thi được batch depth.")

            # Bước 3: nội suy giống PyTorch rồi đồng bộ trước khi trả NumPy.
            depths = []
            for index, (height, width) in enumerate(sizes):
                resized = F.interpolate(
                    outputs[index][None, None].float(),
                    (height, width),
                    mode="bilinear",
                    align_corners=True,
                )[0, 0]
                depth = resized.cpu().numpy()
                if not np.all(np.isfinite(depth)):
                    raise RuntimeError("TensorRT trả về giá trị depth không hữu hạn.")
                depths.append(depth)
            return depths
