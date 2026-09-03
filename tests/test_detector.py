"""Kiểm thử các thành phần cốt lõi của detector."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from occupancy_monitor.config import save_setup
from occupancy_monitor.detection import (
    StableState,
    changed_ratio,
    foreground_mask,
    lab_color_distance,
)
from occupancy_monitor.display import resize_for_display


class DetectorTests(unittest.TestCase):
    """Kiểm tra xử lý ảnh, trạng thái và dữ liệu setup."""

    def test_identical_frames_are_empty(self) -> None:
        """Hai frame giống nhau phải tạo mask hoàn toàn trống."""
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        mask = foreground_mask(frame, frame.copy(), 30, 100)
        self.assertEqual(changed_ratio(mask), 0.0)

    # ─────────────────────────────────────────────────────────────────────────
    def test_large_object_is_detected(self) -> None:
        """Một vật thể đủ lớn phải được giữ lại trong foreground mask."""
        background = np.zeros((200, 300, 3), dtype=np.uint8)
        current = background.copy()
        cv2.rectangle(current, (50, 40), (200, 160), (255, 255, 255), -1)
        mask = foreground_mask(background, current, 30, 100)
        self.assertGreater(changed_ratio(mask), 0.20)

    # ─────────────────────────────────────────────────────────────────────────
    def test_lab_detects_colors_with_similar_grayscale(self) -> None:
        """Lab phải phân biệt hai màu có mức xám gần giống nhau."""
        orange = np.full((100, 100, 3), (0, 140, 255), dtype=np.uint8)
        skin_tone = np.full((100, 100, 3), (100, 160, 190), dtype=np.uint8)
        orange_gray = cv2.cvtColor(orange, cv2.COLOR_BGR2GRAY)
        skin_gray = cv2.cvtColor(skin_tone, cv2.COLOR_BGR2GRAY)
        self.assertLess(abs(int(orange_gray[0, 0]) - int(skin_gray[0, 0])), 10)

        distance = lab_color_distance(
            cv2.cvtColor(orange, cv2.COLOR_BGR2LAB),
            cv2.cvtColor(skin_tone, cv2.COLOR_BGR2LAB),
        )
        self.assertGreater(int(distance[0, 0]), 30)
        mask = foreground_mask(orange, skin_tone, 30, 100)
        self.assertGreater(changed_ratio(mask), 0.95)

    # ─────────────────────────────────────────────────────────────────────────
    def test_small_noise_is_removed(self) -> None:
        """Vùng thay đổi nhỏ hơn ngưỡng contour phải bị loại bỏ."""
        background = np.zeros((200, 300, 3), dtype=np.uint8)
        current = background.copy()
        cv2.rectangle(current, (10, 10), (15, 15), (255, 255, 255), -1)
        mask = foreground_mask(background, current, 30, 250)
        self.assertEqual(changed_ratio(mask), 0.0)

    # ─────────────────────────────────────────────────────────────────────────
    def test_state_is_debounced(self) -> None:
        """Trạng thái chỉ được đổi sau đủ số frame liên tiếp."""
        state = StableState(enter_frames=3, exit_frames=2)
        self.assertFalse(state.update(True))
        self.assertFalse(state.update(True))
        self.assertTrue(state.update(True))
        self.assertTrue(state.update(False))
        self.assertFalse(state.update(False))

    # ─────────────────────────────────────────────────────────────────────────
    def test_display_resize_preserves_aspect_ratio(self) -> None:
        """Thu nhỏ hiển thị phải giữ đúng tỷ lệ khung hình."""
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        resized = resize_for_display(frame, 0.5)
        self.assertEqual(resized.shape, (100, 150, 3))

    # ─────────────────────────────────────────────────────────────────────────
    def test_setup_saves_only_selected_roi(self) -> None:
        """Setup chỉ được lưu hình chữ nhật bao quanh polygon."""
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with (
                patch("occupancy_monitor.config.DATA_DIR", data_dir),
                patch("occupancy_monitor.config.CONFIG_PATH", data_dir / "config.json"),
                patch(
                    "occupancy_monitor.config.BACKGROUND_PATH",
                    data_dir / "background.jpg",
                ),
            ):
                polygon = [[20, 30], [119, 30], [119, 109], [20, 109]]
                save_setup(frame, polygon)
                saved = cv2.imread(str(data_dir / "background.jpg"))
                self.assertEqual(saved.shape, (80, 100, 3))

    # ─────────────────────────────────────────────────────────────────────────
    def test_pixels_outside_polygon_are_ignored(self) -> None:
        """Vùng thay đổi nằm ngoài polygon không được tính là foreground."""
        background = np.zeros((100, 100, 3), dtype=np.uint8)
        current = background.copy()
        cv2.rectangle(current, (70, 70), (99, 99), (255, 255, 255), -1)
        roi_mask = np.zeros((100, 100), dtype=np.uint8)
        cv2.fillPoly(roi_mask, [np.array([[0, 0], [60, 0], [0, 60]])], 255)
        mask = foreground_mask(background, current, 30, 10, roi_mask)
        self.assertEqual(changed_ratio(mask, roi_mask), 0.0)


if __name__ == "__main__":
    unittest.main()
