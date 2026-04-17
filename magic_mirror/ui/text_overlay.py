"""OCR 文本展示覆盖层 — 可选中复制的原文展示窗口。

职责单一：只负责 RenderBlock 的屏幕展示，使用 QTextEdit 实现
原生文本选中 / 复制能力。仅用于 OCR 提取文本模式。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent
from PyQt6.QtWidgets import QApplication, QMenu, QTextEdit, QVBoxLayout, QWidget

from magic_mirror.config.settings import FONT_FAMILY_ZH
from magic_mirror.interfaces.types import RenderBlock
from magic_mirror.ui.context_preview import ContextPreviewPanel

logger = logging.getLogger(__name__)


class TextOverlay(QWidget):
    """OCR 文本覆盖层 — 无边框置顶窗口，文本可选中复制。"""

    # 用户请求打开智能对话
    sig_open_chat = pyqtSignal(str)       # context_text

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        self._render_blocks: List[RenderBlock] = []
        self._win_x = 0
        self._win_y = 0

        # 上下文预览面板
        self._preview = ContextPreviewPanel()

        # 只读文本编辑器 — 支持跨行自由选中
        self._editor = QTextEdit(self)
        self._editor.setReadOnly(True)
        self._editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._editor.customContextMenuRequested.connect(self._show_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._editor)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def init_geometry(self, screen_bbox: Tuple[int, int, int, int]) -> None:
        """初始化覆盖层几何区域（不显示窗口）。"""
        self._win_x = screen_bbox[0]
        self._win_y = screen_bbox[1]
        self.setGeometry(
            screen_bbox[0], screen_bbox[1],
            screen_bbox[2], screen_bbox[3],
        )
        self._preview.clear_texts()
        self._preview.position_beside(screen_bbox)

    def add_block(self, block: RenderBlock) -> None:
        """添加一个渲染块的文本内容。"""
        self._render_blocks.append(block)
        self._rebuild_content()
        self._preview.add_text(block.translated_text)
        if not self.isVisible():
            self.show()
            self.raise_()

    def close_overlay(self) -> None:
        """关闭并清理覆盖层。"""
        self._render_blocks.clear()
        self._editor.clear()
        self._preview.close_panel()
        self.hide()

    def clear(self) -> None:
        """清空渲染内容并隐藏窗口。"""
        self.close_overlay()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _rebuild_content(self) -> None:
        """根据所有 RenderBlock 重建编辑器内容和样式。"""
        if not self._render_blocks:
            return

        # 取第一个块的颜色作为整体样式基准
        first = self._render_blocks[0]
        bg = first.bg_color
        tc = first.text_color
        font_size = first.font_size

        # 样式表
        self._editor.setStyleSheet(
            f"QTextEdit {{"
            f"  background-color: rgba({bg[0]},{bg[1]},{bg[2]},{bg[3]});"
            f"  color: rgb({tc[0]},{tc[1]},{tc[2]});"
            f"  border: none;"
            f"  selection-background-color: rgba(51,144,255,120);"
            f"}}"
        )

        font = QFont(FONT_FAMILY_ZH)
        font.setPixelSize(font_size)
        self._editor.setFont(font)

        # 合并所有块的文本
        lines = [b.translated_text for b in self._render_blocks]
        self._editor.setPlainText("\n".join(lines))

    def _show_menu(self, pos) -> None:
        """自定义右键菜单。"""
        menu = QMenu(self)

        act_copy_sel = menu.addAction("复制选中")
        act_copy_sel.triggered.connect(self._copy_selection)
        act_copy_sel.setEnabled(self._editor.textCursor().hasSelection())

        act_copy_all = menu.addAction("复制全部")
        act_copy_all.triggered.connect(self._copy_all_text)

        act_select_all = menu.addAction("全选")
        act_select_all.triggered.connect(self._editor.selectAll)

        menu.addSeparator()

        act_chat = menu.addAction("智能对话")
        act_chat.triggered.connect(self._open_chat)

        menu.addSeparator()

        act_close = menu.addAction("关闭")
        act_close.triggered.connect(self.close_overlay)

        menu.exec(self._editor.mapToGlobal(pos))

    def _copy_selection(self) -> None:
        """复制选中文本到剪贴板。"""
        self._editor.copy()

    def _copy_all_text(self) -> None:
        """复制所有文本到剪贴板。"""
        text = self._editor.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            logger.debug("已复制全部文本到剪贴板")

    def _open_chat(self) -> None:
        """发射智能对话信号，携带当前所有文本。"""
        text = self._editor.toPlainText()
        if text:
            self.sig_open_chat.emit(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_overlay()
        else:
            super().keyPressEvent(event)
