"""Command line interface cho walkway monitor."""

from __future__ import annotations

import argparse
from pathlib import Path

from utils.logger import LOGGER
from walkway_monitor.calibration.pipeline import CalibrationPipeline
from walkway_monitor.calibration.storage import load_baseline
from walkway_monitor.config import CalibrationConfig, DetectionConfig
from walkway_monitor.depth.estimator import DepthAnythingEstimator
from walkway_monitor.detection.pipeline import DetectionPipeline


def build_parser() -> argparse.ArgumentParser:
    """Tạo parser gốc và các subcommand được hỗ trợ."""
    parser = argparse.ArgumentParser(
        prog="walkway-monitor",
        description="Tạo baseline và giám sát lối đi bằng Depth Anything.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    calibration_parser = subparsers.add_parser(
        "calibrate",
        help="Chọn ROI và tạo baseline từ cảnh lối đi trống.",
    )
    calibration_parser.add_argument(
        "--source",
        required=True,
        help="RTSP/RTMP URL, đường dẫn video hoặc webcam index.",
    )
    calibration_parser.add_argument(
        "--checkpoint",
        help="Checkpoint model; mặc định weights/depth_anything_v2_<encoder>.pth.",
    )
    calibration_parser.add_argument(
        "--encoder",
        default="vits",
        choices=("vits", "vitb", "vitl"),
    )
    calibration_parser.add_argument("--frames", type=int, default=60)
    calibration_parser.add_argument("--input-size", type=int, default=518)
    calibration_parser.add_argument("--process-width", type=int, default=960)
    calibration_parser.add_argument(
        "--output",
        default="data/walkway_baseline.npz",
    )
    calibration_parser.add_argument(
        "--preview",
        help="Đường dẫn ảnh preview; mặc định nằm cạnh file baseline.",
    )
    calibration_parser.add_argument(
        "--no-gstreamer",
        action="store_true",
        help="Bỏ qua GStreamer và mở RTSP bằng FFMPEG.",
    )
    calibration_parser.add_argument("--open-timeout-ms", type=int, default=5000)
    calibration_parser.add_argument("--read-timeout-ms", type=int, default=5000)

    detection_parser = subparsers.add_parser(
        "detect",
        help="So sánh từng full frame với baseline và phát hiện vật cản.",
    )
    detection_parser.add_argument(
        "--source",
        required=True,
        help="RTSP/RTMP URL, đường dẫn video hoặc webcam index.",
    )
    detection_parser.add_argument(
        "--baseline",
        default="data/walkway_baseline.npz",
    )
    detection_parser.add_argument(
        "--checkpoint",
        help="Checkpoint model; mặc định lấy encoder baseline trong thư mục weights/.",
    )
    detection_parser.add_argument("--noise-multiplier", type=float, default=6.0)
    detection_parser.add_argument("--minimum-difference", type=float, default=0.03)
    detection_parser.add_argument("--minimum-area-ratio", type=float, default=0.01)
    detection_parser.add_argument("--occupied-frames", type=int, default=5)
    detection_parser.add_argument("--clear-frames", type=int, default=8)
    detection_parser.add_argument(
        "--camera-difference-threshold",
        type=float,
        default=0.12,
    )
    detection_parser.add_argument(
        "--camera-change-area-ratio",
        type=float,
        default=0.25,
    )
    detection_parser.add_argument("--depth-blur-kernel", type=int, default=5)
    detection_parser.add_argument("--roi-border-margin", type=int, default=6)
    detection_parser.add_argument("--mask-temporal-window", type=int, default=5)
    detection_parser.add_argument("--mask-temporal-required", type=int, default=3)
    detection_parser.add_argument(
        "--display-minimum-area-ratio",
        type=float,
        default=0.001,
    )
    detection_parser.add_argument(
        "--no-display",
        action="store_true",
        help="Không mở cửa sổ OpenCV; phù hợp khi xử lý video tự động.",
    )
    detection_parser.add_argument(
        "--log-interval",
        type=float,
        default=2.0,
        help="Chu kỳ log FPS tính bằng giây; đặt 0 để tắt log định kỳ.",
    )
    detection_parser.add_argument("--no-gstreamer", action="store_true")
    detection_parser.add_argument("--open-timeout-ms", type=int, default=5000)
    detection_parser.add_argument("--read-timeout-ms", type=int, default=5000)
    return parser


# ─────────────────────────────────────────────────────────────────────────────


def parse_source(value: str):
    """Chuyển chuỗi chỉ gồm chữ số thành webcam index, giữ nguyên URL và path."""
    return int(value) if value.isdigit() else value


# ─────────────────────────────────────────────────────────────────────────────


def run_calibration(args: argparse.Namespace) -> int:
    """Khởi tạo các dependency và chạy subcommand calibration."""
    config = CalibrationConfig(
        frame_count=args.frames,
        input_size=args.input_size,
        process_width=args.process_width,
        encoder=args.encoder,
    )
    config.validate()
    checkpoint = args.checkpoint or str(
        Path("weights") / f"depth_anything_v2_{args.encoder}.pth"
    )
    estimator = DepthAnythingEstimator(
        checkpoint=checkpoint,
        encoder=args.encoder,
        input_size=args.input_size,
    )
    pipeline = CalibrationPipeline(estimator=estimator, config=config)
    pipeline.run(
        source=parse_source(args.source),
        output_path=args.output,
        preview_path=args.preview,
        use_gstreamer=not args.no_gstreamer,
        open_timeout_ms=args.open_timeout_ms,
        read_timeout_ms=args.read_timeout_ms,
    )
    return 0


# ─────────────────────────────────────────────────────────────────────────────


def run_detection(args: argparse.Namespace) -> int:
    """Đọc baseline, khởi tạo model và chạy pipeline detection full frame."""
    baseline = load_baseline(args.baseline)
    config = DetectionConfig(
        noise_multiplier=args.noise_multiplier,
        minimum_difference=args.minimum_difference,
        minimum_area_ratio=args.minimum_area_ratio,
        occupied_frames=args.occupied_frames,
        clear_frames=args.clear_frames,
        camera_difference_threshold=args.camera_difference_threshold,
        camera_change_area_ratio=args.camera_change_area_ratio,
        depth_blur_kernel=args.depth_blur_kernel,
        roi_border_margin=args.roi_border_margin,
        mask_temporal_window=args.mask_temporal_window,
        mask_temporal_required=args.mask_temporal_required,
        display_minimum_area_ratio=args.display_minimum_area_ratio,
    )
    config.validate()
    checkpoint = args.checkpoint or str(
        Path("weights") / f"depth_anything_v2_{baseline.encoder}.pth"
    )
    estimator = DepthAnythingEstimator(
        checkpoint=checkpoint,
        encoder=baseline.encoder,
        input_size=baseline.input_size,
    )
    pipeline = DetectionPipeline(
        estimator=estimator,
        baseline=baseline,
        config=config,
        display=not args.no_display,
        log_interval=args.log_interval,
    )
    pipeline.run(
        source=parse_source(args.source),
        use_gstreamer=not args.no_gstreamer,
        open_timeout_ms=args.open_timeout_ms,
        read_timeout_ms=args.read_timeout_ms,
    )
    return 0


# ─────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Parse command line và trả về exit code của command được chọn."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "calibrate":
            return run_calibration(args)
        if args.command == "detect":
            return run_detection(args)
    except KeyboardInterrupt as exc:
        LOGGER.warning("Đã dừng: %s", exc)
        return 130
    except Exception as exc:
        LOGGER.error("Không thể hoàn thành %s: %s", args.command, exc)
        return 1
    parser.error(f"Command không được hỗ trợ: {args.command}")
    return 2
