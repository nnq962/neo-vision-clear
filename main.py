"""Simple fixed-camera occupancy detector using only OpenCV."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np


DATA_DIR = Path("data")
CONFIG_PATH = DATA_DIR / "config.json"
BACKGROUND_PATH = DATA_DIR / "background.jpg"
WINDOW_NAME = "Neo Vision Clear"
DEFAULT_DISPLAY_SCALE = 0.65


@dataclass
class DetectorConfig:
    roi: tuple[int, int, int, int]
    polygon: list[list[int]] | None = None
    frame_width: int = 0
    frame_height: int = 0
    pixel_threshold: int = 30
    occupied_ratio: float = 0.03
    min_contour_area: int = 250
    enter_frames: int = 3
    exit_frames: int = 15


class StableState:
    """Debounce noisy frame decisions before changing the public state."""

    def __init__(self, enter_frames: int, exit_frames: int) -> None:
        self.enter_frames = enter_frames
        self.exit_frames = exit_frames
        self.occupied = False
        self.positive_count = 0
        self.negative_count = 0

    def update(self, detected: bool) -> bool:
        if detected:
            self.positive_count += 1
            self.negative_count = 0
            if self.positive_count >= self.enter_frames:
                self.occupied = True
        else:
            self.negative_count += 1
            self.positive_count = 0
            if self.negative_count >= self.exit_frames:
                self.occupied = False
        return self.occupied


def open_stream(source: str) -> cv2.VideoCapture:
    parsed_source: str | int = int(source) if source.isdigit() else source
    if isinstance(parsed_source, str) and parsed_source.startswith("rtsp://"):
        capture = cv2.VideoCapture(parsed_source, cv2.CAP_FFMPEG)
    else:
        capture = cv2.VideoCapture(parsed_source)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


def read_frame(capture: cv2.VideoCapture, retries: int = 30) -> np.ndarray:
    for _ in range(retries):
        ok, frame = capture.read()
        if ok and frame is not None:
            return frame
        time.sleep(0.1)
    raise RuntimeError("Không đọc được frame từ camera.")


def preprocess(image: np.ndarray) -> np.ndarray:
    """Blur camera noise, then preserve luminance and chroma in Lab space."""
    blurred = cv2.GaussianBlur(image, (5, 5), 0)
    return cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB)


def lab_color_distance(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Return an 8-bit per-pixel Euclidean distance between two Lab images."""
    delta = first.astype(np.float32) - second.astype(np.float32)
    distance = np.sqrt(np.sum(delta * delta, axis=2))
    return np.clip(distance, 0, 255).astype(np.uint8)


def foreground_mask(
    background_roi: np.ndarray,
    current_roi: np.ndarray,
    pixel_threshold: int,
    min_contour_area: int,
    roi_mask: np.ndarray | None = None,
) -> np.ndarray:
    difference = lab_color_distance(
        preprocess(background_roi), preprocess(current_roi)
    )
    _, raw_mask = cv2.threshold(
        difference, pixel_threshold, 255, cv2.THRESH_BINARY
    )
    if roi_mask is not None:
        raw_mask = cv2.bitwise_and(raw_mask, roi_mask)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filtered = np.zeros_like(mask)
    for contour in contours:
        if cv2.contourArea(contour) >= min_contour_area:
            cv2.drawContours(filtered, [contour], -1, 255, thickness=cv2.FILLED)
    if roi_mask is not None:
        filtered = cv2.bitwise_and(filtered, roi_mask)
    return filtered


def changed_ratio(mask: np.ndarray, roi_mask: np.ndarray | None = None) -> float:
    valid_pixels = cv2.countNonZero(roi_mask) if roi_mask is not None else mask.size
    if valid_pixels == 0:
        return 0.0
    return cv2.countNonZero(mask) / float(valid_pixels)


def resize_for_display(image: np.ndarray, scale: float) -> np.ndarray:
    if scale == 1.0:
        return image
    return cv2.resize(
        image,
        dsize=None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA,
    )


def select_polygon(frame: np.ndarray, display_scale: float) -> list[list[int]]:
    window = "Select polygon ROI"
    display_frame = resize_for_display(frame, display_scale)
    points: list[tuple[int, int]] = []

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))
        elif event == cv2.EVENT_RBUTTONDOWN and points:
            points.pop()

    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)
    while True:
        preview = display_frame.copy()
        if points:
            cv2.polylines(
                preview,
                [np.asarray(points, dtype=np.int32)],
                isClosed=len(points) >= 3,
                color=(0, 255, 255),
                thickness=2,
            )
            for point in points:
                cv2.circle(preview, point, 4, (0, 0, 255), thickness=-1)
        cv2.putText(
            preview,
            "Left click: point | Right click: undo | ENTER: save | C: clear",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2,
        )
        cv2.imshow(window, preview)
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10) and len(points) >= 3:
            break
        if key == ord("c"):
            points.clear()
        if key == 27:
            points.clear()
            break

    cv2.destroyWindow(window)
    return [
        [int(round(x / display_scale)), int(round(y / display_scale))]
        for x, y in points
    ]


def save_setup(frame: np.ndarray, polygon: list[list[int]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if len(polygon) < 3:
        raise RuntimeError("Polygon cần ít nhất 3 điểm.")
    points = np.asarray(polygon, dtype=np.int32)
    x, y, width, height = cv2.boundingRect(points)
    roi = (x, y, width, height)
    background_roi = frame[y : y + height, x : x + width]
    if background_roi.size == 0:
        raise RuntimeError("ROI nằm ngoài frame camera.")
    config = DetectorConfig(
        roi=roi,
        polygon=polygon,
        frame_width=frame.shape[1],
        frame_height=frame.shape[0],
    )
    if not cv2.imwrite(str(BACKGROUND_PATH), background_roi):
        raise RuntimeError(f"Không thể lưu ảnh nền vào {BACKGROUND_PATH}.")
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")


def run_setup(source: str, display_scale: float) -> None:
    capture = open_stream(source)
    if not capture.isOpened():
        raise RuntimeError("Không mở được camera. Kiểm tra URL, mạng và tài khoản.")

    print("Đảm bảo khu vực đang trống. Nhấn SPACE để chụp nền, Q để thoát.")
    selected_frame: np.ndarray | None = None
    while True:
        frame = read_frame(capture)
        preview = frame.copy()
        cv2.putText(
            preview,
            "Clear the area, then press SPACE",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )
        cv2.imshow(WINDOW_NAME, resize_for_display(preview, display_scale))
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == 32:
            selected_frame = frame.copy()
            break

    if selected_frame is not None:
        print("Click trái để đặt các đỉnh polygon, rồi nhấn ENTER.")
        polygon = select_polygon(selected_frame, display_scale)
        if len(polygon) < 3:
            raise RuntimeError("Đã hủy hoặc polygon không hợp lệ.")
        save_setup(selected_frame, polygon)
        print(f"Đã lưu riêng ảnh nền polygon trong thư mục {DATA_DIR}/")

    capture.release()
    cv2.destroyAllWindows()


def load_setup() -> tuple[np.ndarray, DetectorConfig]:
    if not CONFIG_PATH.exists() or not BACKGROUND_PATH.exists():
        raise RuntimeError("Chưa có cấu hình. Hãy chạy chương trình với --setup trước.")
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["roi"] = tuple(payload["roi"])
    config = DetectorConfig(**payload)
    background = cv2.imread(str(BACKGROUND_PATH))
    if background is None:
        raise RuntimeError("Ảnh nền bị lỗi hoặc không đọc được.")
    return background, config


def run_detector(source: str, display_scale: float) -> None:
    background, config = load_setup()
    x, y, width, height = config.roi
    # New setups store only the ROI. The second branch keeps old setups usable.
    if background.shape[:2] == (height, width):
        background_roi = background
    else:
        background_roi = background[y : y + height, x : x + width]
        if background_roi.size == 0:
            raise RuntimeError("ROI nằm ngoài ảnh nền.")

    roi_mask: np.ndarray | None = None
    polygon_points: np.ndarray | None = None
    if config.polygon:
        polygon_points = np.asarray(config.polygon, dtype=np.int32)
        relative_points = polygon_points - np.asarray([x, y], dtype=np.int32)
        roi_mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(roi_mask, [relative_points], 255)

    capture = open_stream(source)
    if not capture.isOpened():
        raise RuntimeError("Không mở được camera. Kiểm tra URL, mạng và tài khoản.")

    state = StableState(config.enter_frames, config.exit_frames)
    print("Detector đang chạy. Nhấn Q để thoát, M để bật/tắt cửa sổ mask.")
    show_mask = True
    while True:
        frame = read_frame(capture)
        expected_size = (config.frame_width, config.frame_height)
        if all(expected_size) and frame.shape[1::-1] != expected_size:
            frame = cv2.resize(frame, expected_size)

        current_roi = frame[y : y + height, x : x + width]
        if current_roi.shape[:2] != background_roi.shape[:2]:
            raise RuntimeError("ROI hiện tại không khớp ảnh nền. Hãy chạy --setup lại.")
        mask = foreground_mask(
            background_roi,
            current_roi,
            config.pixel_threshold,
            config.min_contour_area,
            roi_mask,
        )
        ratio = changed_ratio(mask, roi_mask)
        occupied = state.update(ratio >= config.occupied_ratio)

        color = (0, 0, 255) if occupied else (0, 200, 0)
        label = "OCCUPIED" if occupied else "EMPTY"
        if polygon_points is not None:
            cv2.polylines(frame, [polygon_points], True, color, 3)
        else:
            cv2.rectangle(frame, (x, y), (x + width, y + height), color, 3)
        cv2.putText(
            frame,
            f"{label} | changed: {ratio:.1%}",
            (x, max(30, y - 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
        )
        cv2.imshow(WINDOW_NAME, resize_for_display(frame, display_scale))
        if show_mask:
            cv2.imshow("Foreground mask", resize_for_display(mask, display_scale))

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("m"):
            show_mask = not show_mask
            if not show_mask:
                cv2.destroyWindow("Foreground mask")

    capture.release()
    cv2.destroyAllWindows()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect occupancy in a fixed camera ROI without an ML model."
    )
    parser.add_argument(
        "--source",
        default=os.environ.get("CAMERA_RTSP_URL"),
        help="RTSP URL, video path, or webcam index. Defaults to CAMERA_RTSP_URL.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Capture an empty background and select the monitored ROI.",
    )
    parser.add_argument(
        "--display-scale",
        type=float,
        default=DEFAULT_DISPLAY_SCALE,
        help="Window scale in the range (0, 1]. Defaults to 0.65.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.source:
        print(
            "Thiếu nguồn video. Đặt CAMERA_RTSP_URL hoặc truyền --source.",
            file=sys.stderr,
        )
        return 2
    if not 0 < args.display_scale <= 1:
        print("--display-scale phải lớn hơn 0 và không vượt quá 1.", file=sys.stderr)
        return 2
    try:
        if args.setup:
            run_setup(args.source, args.display_scale)
        else:
            run_detector(args.source, args.display_scale)
    except (RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Lỗi: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
