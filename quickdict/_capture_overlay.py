"""
_capture_overlay.py — OCR 截图区域可视化。

职责单一：在屏幕上绘制一个半透明矩形框，标示 OCR 截图范围。
不含取词、OCR、弹窗等逻辑，仅负责绘制和定位。
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget, QApplication

import quickdict._ocr_capture as _ocr_capture


class CaptureRegionOverlay(QWidget):
    """半透明矩形框，显示 OCR 截图区域。"""

    _BORDER_COLOR = QColor(67, 97, 238, 160)   # 蓝色边框
    _BORDER_WIDTH = 2
    _HIDE_DELAY_MS = 1500                       # 自动隐藏延时

    def __init__(self):
        super().__init__()
        self._fill_color = QColor(67, 97, 238, 15)  # 可调填充色
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def set_fill_opacity(self, alpha: int):
        """设置填充透明度 (0-255)。"""
        self._fill_color = QColor(67, 97, 238, max(0, min(255, alpha)))

    def show_at(self, x: int, y: int):
        """在鼠标 (x, y) 周围显示截图区域框。"""
        scale = _ocr_capture._get_screen_scale()
        hw = int(_ocr_capture._HALF_W * scale)
        hh = int(_ocr_capture._HALF_H * scale)

        # 全局屏幕坐标 → 窗口位置和大小
        left = x - hw
        top = y - hh
        w = hw * 2
        h = hh * 2

        self.setGeometry(left, top, w, h)
        self.show()
        self.raise_()

        self._hide_timer.stop()
        self._hide_timer.start(self._HIDE_DELAY_MS)

    def hide_box(self):
        """立即隐藏。"""
        self._hide_timer.stop()
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 淡填充
        p.fillRect(self.rect(), self._fill_color)
        # 边框
        pen = QPen(self._BORDER_COLOR, self._BORDER_WIDTH)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(1, 1, -1, -1))
        p.end()
