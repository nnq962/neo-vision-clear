"""Tiện ích hiển thị giao diện và chữ Unicode trên frame."""

from .text import draw_text
from .detection_view import DetectionViewRenderer, render_detection_view

__all__ = ["DetectionViewRenderer", "draw_text", "render_detection_view"]
