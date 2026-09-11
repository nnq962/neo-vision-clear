"""Kiểm thử các flag của command line interface."""

import unittest

from walkway_monitor.cli import build_parser


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


if __name__ == "__main__":
    unittest.main()
