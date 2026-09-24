"""Kiểm thử các flag của command line interface."""

import unittest

from walkway_monitor.cli import build_parser
from walkway_monitor.config import DEFAULT_BASELINE_PATH
from walkway_monitor.config import DEFAULT_INFERENCE_BATCH_SIZE


class CliParserTestCase(unittest.TestCase):
    """Kiểm tra giá trị mặc định và tùy chọn của CLI."""

    def test_depth_heatmap_flags(self) -> None:
        """Hai flag heatmap phải bật và tắt đúng cấu hình hiển thị."""
        parser = build_parser()

        default_args = parser.parse_args(["detect", "--source", "video.mp4"])
        hidden_args = parser.parse_args(
            ["detect", "--source", "video.mp4", "--no-depth-heatmaps"]
        )
        shown_args = parser.parse_args(
            ["detect", "--source", "video.mp4", "--depth-heatmaps"]
        )

        self.assertTrue(default_args.depth_heatmaps)
        self.assertFalse(hidden_args.depth_heatmaps)
        self.assertTrue(shown_args.depth_heatmaps)

    # ─────────────────────────────────────────────────────────────────────────

    def test_uses_grouped_default_baseline_path(self) -> None:
        """Hai command mặc định phải đọc và ghi cùng baseline trong thư mục riêng."""
        parser = build_parser()

        calibration_args = parser.parse_args(["calibrate", "--source", "video.mp4"])
        detection_args = parser.parse_args(["detect", "--source", "video.mp4"])

        self.assertEqual(calibration_args.output, DEFAULT_BASELINE_PATH)
        self.assertIsNone(detection_args.baseline)

    # ─────────────────────────────────────────────────────────────────────────

    def test_metric_measurement_argument(self) -> None:
        """CLI phải parse được độ phân giải BEV theo mét."""
        parser = build_parser()
        args = parser.parse_args(
            [
                "detect",
                "--source",
                "video.mp4",
                "--bev-pixels-per-meter",
                "120",
            ]
        )

        self.assertEqual(args.bev_pixels_per_meter, 120.0)

    # ─────────────────────────────────────────────────────────────────────────

    def test_inference_batch_size_arguments(self) -> None:
        """Hai command phải có batch mặc định và nhận được giá trị tùy chỉnh."""
        parser = build_parser()

        calibration_args = parser.parse_args(
            ["calibrate", "--source", "video.mp4", "--batch-size", "4"]
        )
        detection_args = parser.parse_args(["detect", "--source", "video.mp4"])

        self.assertEqual(calibration_args.batch_size, 4)
        self.assertEqual(
            detection_args.batch_size,
            DEFAULT_INFERENCE_BATCH_SIZE,
        )

    # ─────────────────────────────────────────────────────────────────────────

    def test_repeated_sources_and_baselines_preserve_order(self) -> None:
        """CLI phải giữ đúng thứ tự ghép cặp hai RTSP và hai baseline."""
        parser = build_parser()
        args = parser.parse_args(
            [
                "detect",
                "--source",
                "rtsp://camera-1/stream",
                "--source",
                "rtsp://camera-2/stream",
                "--baseline",
                "data/camera-1/baseline.npz",
                "--baseline",
                "data/camera-2/baseline.npz",
            ]
        )

        self.assertEqual(
            args.source,
            ["rtsp://camera-1/stream", "rtsp://camera-2/stream"],
        )
        self.assertEqual(
            args.baseline,
            ["data/camera-1/baseline.npz", "data/camera-2/baseline.npz"],
        )


if __name__ == "__main__":
    unittest.main()
