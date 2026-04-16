"""屏幕截图协议"""

from __future__ import annotations

from typing import Protocol, Tuple

from .types import CaptureResult


class IScreenCapture(Protocol):
    """对指定矩形区域截图"""

    def capture(self, bbox: Tuple[int, int, int, int]) -> CaptureResult:
        """bbox: (x, y, w, h) 屏幕坐标 → 截图结果"""
        ...
