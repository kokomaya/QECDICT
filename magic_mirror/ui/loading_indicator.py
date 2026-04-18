"""加载动画指示器 — 翻译等待时在选定区域显示旋转圆弧 + 提示文字。

职责单一：只负责加载状态的视觉反馈，不涉及翻译逻辑或管线控制。
"""

from __future__ import annotations

from typing import Tuple

from PyQt6.QtCore import QPropertyAnimation, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

from magic_mirror.config.settings import FONT_FAMILY_ZH

# 动画参数
_INDICATOR_SIZE = 120          # 指示器窗口边长
_ARC_RADIUS = 28               # 圆弧半径
_ARC_WIDTH = 4                 # 圆弧线宽
_ARC_SPAN = 270 * 16           # 圆弧跨度 (Qt 用 1/16 度)
_ROTATE_STEP = 10              # 每帧旋转度数
_ROTATE_INTERVAL_MS = 30       # 刷新间隔
_FADE_DURATION_MS = 200        # 淡出动画时长


class LoadingIndicator(QWidget):
    """翻译加载指示器 — 无边框置顶半透明窗口，旋转圆弧 + 提示文字。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(_INDICATOR_SIZE, _INDICATOR_SIZE)

        self._angle = 0
        self._hint_text = "翻译中..."

        # 旋转定时器
        self._timer = QTimer(self)
        self._timer.setInterval(_ROTATE_INTERVAL_MS)
        self._timer.timeout.connect(self._rotate)

        # 淡出效果
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def show_at(self, screen_bbox: Tuple[int, int, int, int], hint: str = "翻译中...") -> None:
        """在 screen_bbox 区域中心显示加载动画。

        Args:
            screen_bbox: (x, y, w, h) 屏幕区域。
            hint: 提示文字。
        """
        cx = screen_bbox[0] + screen_bbox[2] // 2
        cy = screen_bbox[1] + screen_bbox[3] // 2
        self.move(cx - _INDICATOR_SIZE // 2, cy - _INDICATOR_SIZE // 2)

        self._hint_text = hint
        self._opacity_effect.setOpacity(1.0)
        self._angle = 0
        self._timer.start()
        self.show()

    def dismiss(self) -> None:
        """淡出并隐藏指示器。"""
        self._timer.stop()

        anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim.setDuration(_FADE_DURATION_MS)
        anim.setStartValue(self._opacity_effect.opacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self.hide)
        anim.start()
        # 保持引用防止被 GC
        self._fade_anim = anim

    def dismiss_immediately(self) -> None:
        """立刻隐藏指示器（无动画）。

        用于在隐藏后紧接着要 show() 其他 Tool 窗口的场景，
        避免 Windows 将本窗口设为新窗口的 native owner。
        """
        self._timer.stop()
        self.hide()

    # ------------------------------------------------------------------
    # Qt 事件
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # 半透明圆角背景
        painter.setBrush(QColor(0, 0, 0, 160))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 12, 12)

        # 旋转圆弧
        cx, cy = w // 2, h // 2 - 10
        arc_rect = QRect(
            cx - _ARC_RADIUS, cy - _ARC_RADIUS,
            _ARC_RADIUS * 2, _ARC_RADIUS * 2,
        )
        pen = QPen(QColor(0, 120, 215), _ARC_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(arc_rect, self._angle * 16, _ARC_SPAN)

        # 提示文字
        font = QFont(FONT_FAMILY_ZH, 11)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        text_rect = QRect(0, cy + _ARC_RADIUS + 4, w, 24)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignHCenter), self._hint_text)

        painter.end()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _rotate(self) -> None:
        """定时器回调：更新旋转角度并重绘。"""
        self._angle = (self._angle + _ROTATE_STEP) % 360
        self.update()