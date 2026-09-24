"""Vẽ chữ Unicode lên frame OpenCV bằng Pillow."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


_FONT_CANDIDATES = (
    "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


@lru_cache(maxsize=16)
def _load_font(font_size: int) -> ImageFont.FreeTypeFont:
    """Tìm và cache một font TrueType có khả năng hiển thị tiếng Việt."""
    if font_size <= 0:
        raise ValueError("Kích thước font phải là số dương.")
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, font_size)
        except OSError:
            continue
    searched = ", ".join(str(Path(item)) for item in _FONT_CANDIDATES)
    raise RuntimeError(f"Không tìm thấy font Unicode. Đã thử: {searched}")


# ─────────────────────────────────────────────────────────────────────────────


def draw_text(
    frame: np.ndarray,
    text: str,
    origin: tuple[int, int],
    font_size: int = 22,
    color: tuple[int, int, int] = (255, 255, 255),
    stroke_width: int = 1,
    stroke_color: tuple[int, int, int] = (0, 0, 0),
) -> np.ndarray:
    """Vẽ chuỗi Unicode lên frame BGR và trả về một frame mới."""
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("Frame phải là numpy.ndarray BGR ba channel.")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    drawer = ImageDraw.Draw(image)
    drawer.text(
        origin,
        text,
        font=_load_font(font_size),
        fill=(color[2], color[1], color[0]),
        stroke_width=stroke_width,
        stroke_fill=(stroke_color[2], stroke_color[1], stroke_color[0]),
    )
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
