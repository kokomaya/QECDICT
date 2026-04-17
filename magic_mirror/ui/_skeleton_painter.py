"""骨架屏绘制器 — 管理骨架占位条的 shimmer 动画与绘制。

单一职责：仅处理骨架屏的状态管理、shimmer 动画驱动和 QPainter 绘制，
不涉及翻译逻辑或覆盖层其他元素的渲染。
参考 Material Design skeleton loading 标准动画效果。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, TYPE_CHECKING

from PyQt6.QtCore import QEasingCurve, QVariantAnimation
from PyQt6.QtGui import QColor, QLinearGradient, QPainter

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

# ── 骨架屏配色 ──
_SKELETON_BG = QColor(200, 200, 200, 180)
_SHIMMER_HIGHLIGHT = QColor(230, 230, 230, 220)

# ── shimmer 动画参数 ──
_SHIMMER_DURATION_MS = 1500
_SHIMMER_WIDTH_RATIO = 0.4


@dataclass
class SkeletonRect:
    """骨架屏占位矩形（屏幕坐标系）。"""

    screen_x: int
    screen_y: int
    w: int
    h: int


class SkeletonPainter:
    """管理骨架屏占位条的 shimmer 动画与绘制。

    使用 QVariantAnimation 驱动一条高亮条从左到右循环滑动，
    模拟 Material Design 的 skeleton shimmer 效果。
    """

    def __init__(self, owner: QWidget) -> None:
        self._owner = owner
        self._rects: List[SkeletonRect] = []
        self._shimmer_t: float = 0.0
        self._anim: QVariantAnimation | None = None

    @property
    def has_skeletons(self) -> bool:
        return bool(self._rects)

    def set_rects(self, rects: List[SkeletonRect]) -> None:
        """设置骨架矩形列表并启动 shimmer 动画。"""
        self._rects = rects
        if rects:
            self._start_anim()
        else:
            self._stop_anim()

    def remove_overlapping(self, sx: int, sy: int, w: int, h: int) -> None:
        """移除与给定屏幕矩形重叠的骨架。"""
        self._rects = [
            r for r in self._rects
            if not _rects_overlap(r.screen_x, r.screen_y, r.w, r.h, sx, sy, w, h)
        ]
        if not self._rects:
            self._stop_anim()

    def clear(self) -> None:
        """清除所有骨架并停止动画。"""
        self._rects.clear()
        self._stop_anim()

    def paint(self, painter: QPainter) -> None:
        """在 owner 坐标系中绘制所有骨架条及 shimmer 高亮。"""
        if not self._rects:
            return
        win_x = self._owner.x()
        win_y = self._owner.y()
        for r in self._rects:
            lx = r.screen_x - win_x
            ly = r.screen_y - win_y
            # 底色
            painter.fillRect(lx, ly, r.w, r.h, _SKELETON_BG)
            # shimmer 高亮条
            shimmer_w = max(int(r.w * _SHIMMER_WIDTH_RATIO), 8)
            total_travel = r.w + shimmer_w
            offset = int(self._shimmer_t * total_travel) - shimmer_w
            gx = lx + offset
            grad = QLinearGradient(gx, 0, gx + shimmer_w, 0)
            grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            grad.setColorAt(0.5, _SHIMMER_HIGHLIGHT)
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.save()
            painter.setClipRect(lx, ly, r.w, r.h)
            painter.fillRect(gx, ly, shimmer_w, r.h, grad)
            painter.restore()

    # ------------------------------------------------------------------
    # 动画控制
    # ------------------------------------------------------------------

    def _start_anim(self) -> None:
        if self._anim is not None:
            return
        anim = QVariantAnimation(self._owner)
        anim.setDuration(_SHIMMER_DURATION_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.setLoopCount(-1)
        anim.valueChanged.connect(self._tick)
        anim.start()
        self._anim = anim

    def _stop_anim(self) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None
        self._shimmer_t = 0.0

    def _tick(self, value) -> None:
        self._shimmer_t = float(value)
        self._owner.update()


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------

def _rects_overlap(
    x1: int, y1: int, w1: int, h1: int,
    x2: int, y2: int, w2: int, h2: int,
) -> bool:
    """两个矩形是否有重叠区域。"""
    return not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)
