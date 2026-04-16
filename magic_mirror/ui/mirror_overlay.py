"""魔法镜子覆盖窗口 — 在屏幕上渲染翻译后的中文覆盖层。

职责单一：只负责 RenderBlock 的屏幕绘制，
不涉及翻译逻辑、排版计算或颜色采样。
支持多行文本（translated_text 可包含 \\n）。
"""

from __future__ import annotations

from typing import List, Tuple

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QKeyEvent, QTextOption
from PyQt6.QtWidgets import QWidget

from magic_mirror.config.settings import FONT_FAMILY_ZH
from magic_mirror.interfaces.types import RenderBlock, TextAlignment

# 映射 TextAlignment → Qt AlignmentFlag
_ALIGN_MAP = {
    TextAlignment.LEFT: Qt.AlignmentFlag.AlignLeft,
    TextAlignment.CENTER: Qt.AlignmentFlag.AlignHCenter,
    TextAlignment.RIGHT: Qt.AlignmentFlag.AlignRight,
}


class MirrorOverlay(QWidget):
    """屏幕翻译覆盖层 — 无边框置顶透明窗口。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._render_blocks: List[RenderBlock] = []
        self._win_x = 0
        self._win_y = 0

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def render(
        self,
        render_blocks: List[RenderBlock],
        screen_bbox: Tuple[int, int, int, int],
    ) -> None:
        """显示覆盖层并渲染翻译文本块。

        Args:
            render_blocks: 可渲染的文本块列表。
            screen_bbox: 截图对应的屏幕区域 (x, y, w, h)。
        """
        self._render_blocks = render_blocks
        self._win_x = screen_bbox[0]
        self._win_y = screen_bbox[1]

        self.setGeometry(
            screen_bbox[0], screen_bbox[1],
            screen_bbox[2], screen_bbox[3],
        )
        self.update()
        self.show()

    def close_overlay(self) -> None:
        """关闭并隐藏覆盖层。"""
        self._render_blocks = []
        self.hide()

    def clear(self) -> None:
        """清空渲染内容并隐藏窗口。"""
        self.close_overlay()

    # ------------------------------------------------------------------
    # Qt 事件
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._render_blocks:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        for block in self._render_blocks:
            # 屏幕绝对坐标 → 窗口局部坐标
            lx = block.screen_x - self._win_x
            ly = block.screen_y - self._win_y

            # 背景矩形
            bg = block.bg_color
            painter.fillRect(
                lx, ly, block.width, block.height,
                QColor(bg[0], bg[1], bg[2], bg[3]),
            )

            # 字体
            font = QFont(FONT_FAMILY_ZH, block.font_size)
            painter.setFont(font)

            # 文字颜色
            tc = block.text_color
            painter.setPen(QColor(tc[0], tc[1], tc[2]))

            # 根据对齐方式构建 QTextOption
            h_align = _ALIGN_MAP.get(block.alignment, Qt.AlignmentFlag.AlignLeft)
            text_opt = QTextOption(h_align | Qt.AlignmentFlag.AlignTop)
            text_opt.setWrapMode(QTextOption.WrapMode.WordWrap)

            # 绘制多行文本
            rect = QRectF(lx, ly, block.width, block.height)
            painter.drawText(rect, block.translated_text, text_opt)

        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_overlay()
        else:
            super().keyPressEvent(event)