"""上下文预览面板 — 在覆盖层右侧显示提取/翻译的文本摘要。

小型浮动面板，随覆盖层同步显示，实时展示原文与译文的双语对照，
方便用户快速对比而无需打开智能对话。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from magic_mirror.config.settings import FONT_FAMILY_ZH

logger = logging.getLogger(__name__)

# 面板固定宽度
_PANEL_WIDTH = 280
# 面板与覆盖层的间距
_GAP = 6
# 面板最小高度
_MIN_HEIGHT = 120


@dataclass
class _TextPair:
    """一组原文+译文。"""
    source: str
    translated: str


class ContextPreviewPanel(QWidget):
    """上下文预览浮动面板 — 显示已提取/翻译文本的只读摘要。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(_PANEL_WIDTH)

        self._texts: List[_TextPair] = []

        # ── 布局 ──
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 容器（用于绘制圆角背景）
        container = QWidget(self)
        container.setObjectName("previewContainer")
        root.addWidget(container)

        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(10, 8, 10, 10)
        vbox.setSpacing(4)

        # 标题
        title = QLabel("上下文预览")
        title.setObjectName("previewTitle")
        vbox.addWidget(title)

        # 文本区域
        self._editor = QTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setObjectName("previewEditor")
        vbox.addWidget(self._editor)

        self._apply_style()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    @property
    def has_content(self) -> bool:
        """面板是否有文本内容。"""
        return bool(self._texts)

    def position_beside(self, overlay_bbox: Tuple[int, int, int, int]) -> None:
        """将面板定位在覆盖层右侧（空间不足时移至左侧）。

        Args:
            overlay_bbox: 覆盖层的屏幕区域 (x, y, w, h)。
        """
        ox, oy, ow, oh = overlay_bbox
        panel_h = max(oh, _MIN_HEIGHT)

        # 获取覆盖层所在屏幕的可用区域
        screen = QGuiApplication.screenAt(
            self.mapFromGlobal(self.pos())
        ) or QGuiApplication.primaryScreen()
        screen_rect = screen.availableGeometry()

        # 优先放在右侧
        right_x = ox + ow + _GAP
        if right_x + _PANEL_WIDTH <= screen_rect.right():
            self.setGeometry(right_x, oy, _PANEL_WIDTH, panel_h)
        else:
            # 右侧空间不足 → 放左侧
            left_x = ox - _PANEL_WIDTH - _GAP
            self.setGeometry(max(left_x, screen_rect.left()), oy, _PANEL_WIDTH, panel_h)

    def add_text(self, translated: str, source: str = "") -> None:
        """增量添加一组原文+译文并刷新双语对照显示。"""
        self._texts.append(_TextPair(source=source, translated=translated))
        self._refresh_display()
        # 滚动到底部
        sb = self._editor.verticalScrollBar()
        sb.setValue(sb.maximum())
        if not self.isVisible():
            self.show()
            self.raise_()

    def clear_texts(self) -> None:
        """清空所有文本。"""
        self._texts.clear()
        self._editor.clear()

    def close_panel(self) -> None:
        """关闭并隐藏面板。"""
        self._texts.clear()
        self._editor.clear()
        self.hide()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _refresh_display(self) -> None:
        """根据当前文本对列表重建富文本内容。"""
        html_parts: List[str] = []
        for pair in self._texts:
            if pair.source:
                html_parts.append(
                    f'<p style="color:rgba(180,180,180,200);margin:2px 0 0 0;">{_esc(pair.source)}</p>'
                    f'<p style="color:rgba(255,255,255,220);margin:0 0 6px 0;">{_esc(pair.translated)}</p>'
                )
            else:
                html_parts.append(
                    f'<p style="color:rgba(255,255,255,220);margin:0 0 6px 0;">{_esc(pair.translated)}</p>'
                )
        self._editor.setHtml("".join(html_parts))

    def _apply_style(self) -> None:
        font = QFont(FONT_FAMILY_ZH)
        font.setPixelSize(13)

        self.setStyleSheet("""
            #previewContainer {
                background-color: rgba(30, 30, 30, 230);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 8px;
            }
            #previewTitle {
                color: rgba(255, 255, 255, 180);
                font-size: 12px;
                font-weight: bold;
                padding: 2px 0;
            }
            #previewEditor {
                background-color: transparent;
                color: rgba(255, 255, 255, 220);
                border: none;
                selection-background-color: rgba(51, 144, 255, 120);
            }
        """)
        self._editor.setFont(font)


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------

def _esc(text: str) -> str:
    """HTML 转义，保留换行。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
