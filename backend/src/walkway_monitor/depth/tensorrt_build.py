"""Xuất Depth Anything V2 sang ONNX và build TensorRT engine tĩnh."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import torch

from depth_anything_v2.dpt import DepthAnythingV2, prepare_image
from walkway_monitor.depth.estimator import MODEL_CONFIGS


def build_parser() -> argparse.ArgumentParser:
    """Khai báo shape của camera và vị trí engine cần tạo."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--encoder", choices=tuple(MODEL_CONFIGS), default="vits")
    parser.add_argument("--input-size", type=int, required=True)
    parser.add_argument("--frame-width", type=int, required=True)
    parser.add_argument("--frame-height", type=int, required=True)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument(
        "--trtexec",
        type=Path,
        default=Path("/usr/src/tensorrt/bin/trtexec"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Xuất ONNX opset 16, build engine FP16 và lưu manifest kiểm tra."""
    args = build_parser().parse_args(argv)
    if min(args.input_size, args.frame_width, args.frame_height, args.batch) <= 0:
        raise ValueError("Kích thước ảnh và batch phải là số dương.")
    if not args.checkpoint.is_file():
        raise FileNotFoundError(args.checkpoint)
    if not args.trtexec.is_file():
        raise FileNotFoundError(args.trtexec)
    try:
        import onnx
    except ImportError as exc:
        raise RuntimeError("Cần cài extra tensorrt-export để xuất ONNX.") from exc

    # Bước 1: lấy shape thực bằng đúng transform của pipeline PyTorch.
    frame = np.zeros((args.frame_height, args.frame_width, 3), dtype=np.uint8)
    image, _size = prepare_image(frame, args.input_size)
    input_shape = [args.batch] + list(image.shape)
    example = torch.zeros(input_shape, dtype=torch.float32)

    # Bước 2: dùng opset 16 vì TensorRT 8.5.2 chưa parse được LayerNormalization
    # nguyên khối mà exporter tạo ra ở opset 17.
    model = DepthAnythingV2(**MODEL_CONFIGS[args.encoder]).cpu().eval()
    model.load_state_dict(
        torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    )
    args.engine.parent.mkdir(parents=True, exist_ok=True)
    onnx_path = args.engine.with_suffix(".onnx")
    with torch.no_grad():
        torch.onnx.export(
            model,
            example,
            str(onnx_path),
            opset_version=16,
            input_names=["input"],
            output_names=["depth"],
            do_constant_folding=True,
        )
    onnx.checker.check_model(str(onnx_path))
    del model

    # Bước 3: build engine trên chính Jetson sẽ chạy inference.
    subprocess.run(
        [
            str(args.trtexec),
            f"--onnx={onnx_path}",
            f"--saveEngine={args.engine}",
            "--fp16",
            "--buildOnly",
            "--memPoolSize=workspace:512",
        ],
        check=True,
    )
    if not args.engine.is_file():
        raise RuntimeError("trtexec không tạo TensorRT engine.")

    # Bước 4: ghi manifest sau khi build xong để runtime từ chối engine sai.
    digest = hashlib.sha256()
    with args.checkpoint.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    metadata = {
        "schema_version": 1,
        "encoder": args.encoder,
        "input_size": args.input_size,
        "input_shape": input_shape,
        "precision": "fp16",
        "checkpoint_sha256": digest.hexdigest(),
    }
    Path(f"{args.engine}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"TensorRT engine: {args.engine}; input={input_shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
