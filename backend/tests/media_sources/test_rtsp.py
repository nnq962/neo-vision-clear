"""Kiểm thử pipeline GStreamer dành cho RTSP và Jetson."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from media_sources.readers.rtsp import RtspReader


class RtspReaderPipelineTestCase(unittest.TestCase):
    """Xác nhận reader chọn đúng decoder và giữ cấu hình low-latency."""

    # ─────────────────────────────────────────────────────────────────────────

    def test_jetson_pipeline_uses_hardware_decoder(self) -> None:
        """Jetson phải dùng nvv4l2decoder và chuyển NVMM về BGR cho OpenCV."""
        with patch.object(RtspReader, "_is_jetson_platform", return_value=True):
            reader = RtspReader(
                "rtsp://camera/stream",
                jetson_hardware_decode=True,
                gstreamer_latency_ms=75,
            )

        pipeline = reader._build_gstreamer_pipeline(
            "rtsp://camera/stream",
            "h264",
        )

        self.assertIn("latency=75", pipeline)
        self.assertIn("h264parse ! nvv4l2decoder", pipeline)
        self.assertIn("nvvidconv ! video/x-raw,format=BGRx", pipeline)
        self.assertIn("video/x-raw,format=BGR", pipeline)
        self.assertIn("queue leaky=downstream max-size-buffers=1", pipeline)
        self.assertNotIn("avdec_h264", pipeline)

    # ─────────────────────────────────────────────────────────────────────────

    def test_non_jetson_pipeline_keeps_software_decoder(self) -> None:
        """Máy thường phải giữ decoder GStreamer CPU và không gọi plugin NVIDIA."""
        with patch.object(RtspReader, "_is_jetson_platform", return_value=False):
            reader = RtspReader(
                "rtsp://camera/stream",
                jetson_hardware_decode=True,
            )

        pipeline = reader._build_gstreamer_pipeline(
            "rtsp://camera/stream",
            "h265",
        )

        self.assertIn("h265parse ! avdec_h265 ! videoconvert", pipeline)
        self.assertNotIn("nvv4l2decoder", pipeline)
        self.assertNotIn("nvvidconv", pipeline)

    # ─────────────────────────────────────────────────────────────────────────

    def test_hardware_decode_can_be_disabled_on_jetson(self) -> None:
        """Cấu hình tắt hardware decode phải buộc reader dùng pipeline CPU."""
        with patch.object(RtspReader, "_is_jetson_platform", return_value=True):
            reader = RtspReader(
                "rtsp://camera/stream",
                jetson_hardware_decode=False,
            )

        pipeline = reader._build_gstreamer_pipeline(
            "rtsp://camera/stream",
            "h264",
        )

        self.assertIn("avdec_h264", pipeline)
        self.assertNotIn("nvv4l2decoder", pipeline)

    # ─────────────────────────────────────────────────────────────────────────

    def test_rejects_negative_gstreamer_latency(self) -> None:
        """Latency âm phải bị từ chối trước khi mở camera."""
        with self.assertRaisesRegex(ValueError, "không được là số âm"):
            RtspReader(
                "rtsp://camera/stream",
                gstreamer_latency_ms=-1,
            )


if __name__ == "__main__":
    unittest.main()
