"""聊天消息 HTML 视图 — 基于 QTextBrowser 的富文本渲染组件。

替代原 QWebEngineView 实现，省去 ~350MB 的 Chromium 依赖。
支持 HTML 子集渲染（加粗、斜体、代码块、列表等）。
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QTextBrowser, QWidget

from magic_mirror.ui.md_renderer import MESSAGE_CSS


class ChatHtmlView(QTextBrowser):
    """轻量 HTML 视图 — 渲染聊天消息。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setReadOnly(True)
        self.setFont(QFont("Microsoft YaHei", 10))
        self.document().setDefaultStyleSheet(MESSAGE_CSS)
        self.setStyleSheet(
            "QTextBrowser {"
            "  background: #212121;"
            "  color: #e0e0e0;"
            "  border: none;"
            "  padding: 8px;"
            "}"
        )

    def set_messages_html(self, body_html: str) -> None:
        scroll = self.verticalScrollBar()
        at_bottom = scroll.value() >= scroll.maximum() - 40

        self.setHtml(f"<html><body>{body_html}</body></html>")

        if at_bottom:
            scroll.setValue(scroll.maximum())

    def clear_view(self) -> None:
        self.clear()
