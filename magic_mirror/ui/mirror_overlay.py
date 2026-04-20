"""魔法镜子覆盖窗口 — 在屏幕上渲染翻译后的中文覆盖层。

职责单一：只负责 RenderBlock / 骨架屏的屏幕绘制与右键交互，
不涉及翻译逻辑、排版计算或颜色采样。
支持多行文本（translated_text 可包含 \\n）。
支持骨架屏占位：OCR 完成后显示灰色占位条，翻译到达后淡入替换。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from PyQt6.QtCore import QRectF, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QTextOption
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from magic_mirror.config.settings import FONT_FAMILY_ZH
from magic_mirror.interfaces.types import RenderBlock, TextAlignment, TextBlock
from magic_mirror.ui._skeleton_painter import SkeletonPainter, SkeletonRect
from magic_mirror.ui.context_preview import ContextPreviewPanel

logger = logging.getLogger(__name__)

# 映射 TextAlignment → Qt AlignmentFlag
_ALIGN_MAP = {
    TextAlignment.LEFT: Qt.AlignmentFlag.AlignLeft,
    TextAlignment.CENTER: Qt.AlignmentFlag.AlignHCenter,
    TextAlignment.RIGHT: Qt.AlignmentFlag.AlignRight,
}

# 错误提示配色
_ERROR_BG = QColor(220, 38, 38, 200)
_ERROR_TEXT = QColor(255, 255, 255)

# 淡入动画时长 (ms)
_FADE_IN_DURATION = 250


class MirrorOverlay(QWidget):
    """屏幕翻译覆盖层 — 无边框置顶透明窗口。"""

    # 用户请求对此覆盖层区域重新翻译
    sig_retranslate = pyqtSignal(tuple)   # screen_bbox (x, y, w, h)
    # 用户请求打开智能对话
    sig_open_chat = pyqtSignal(str)       # context_text
    # 覆盖层拖拽 / 缩放后几何变化
    sig_geometry_changed = pyqtSignal(tuple)   # (x, y, w, h)

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
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._render_blocks: List[RenderBlock] = []
        self._block_opacity: float = 1.0           # 用于淡入动画
        self._fade_anim: QVariantAnimation | None = None
        self._win_x = 0
        self._win_y = 0

        # 骨架屏绘制（shimmer 动画）
        self._skeleton_painter = SkeletonPainter(self)
        # 上下文预览面板
        self._preview = ContextPreviewPanel()
        self._error_msg: str | None = None   # 错误提示文本
        self._peeking: bool = False          # Space 键"透视"原文模式

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def render(
        self,
        render_blocks: List[RenderBlock],
        screen_bbox: Tuple[int, int, int, int],
    ) -> None:
        """显示覆盖层并渲染翻译文本块。"""
        self._render_blocks = render_blocks
        self._skeleton_painter.clear()
        self._win_x = screen_bbox[0]
        self._win_y = screen_bbox[1]

        self.setGeometry(
            screen_bbox[0], screen_bbox[1],
            screen_bbox[2], screen_bbox[3],
        )
        self.update()
        self.show()

    def init_geometry(self, screen_bbox: Tuple[int, int, int, int]) -> None:
        """初始化覆盖层几何区域（不显示窗口）。

        仅设置窗口位置和大小，后续通过 set_skeletons / add_block 触发显示。
        避免在 LoadingIndicator 可见期间 show()，防止 Windows Tool 窗口
        所有权链导致覆盖层随 loading 一起被隐藏。
        """
        self._render_blocks = []
        self._skeleton_painter.clear()
        self._win_x = screen_bbox[0]
        self._win_y = screen_bbox[1]
        self.setGeometry(
            screen_bbox[0], screen_bbox[1],
            screen_bbox[2], screen_bbox[3],
        )
        self._preview.clear_texts()
        self._preview.position_beside(screen_bbox)

    def set_skeletons(
        self,
        text_blocks: List[TextBlock],
        screen_bbox: Tuple[int, int, int, int],
    ) -> None:
        """OCR 完成后显示灰色骨架占位条。

        Args:
            text_blocks: OCR 识别出的文本块列表（用其 bbox 计算位置）。
            screen_bbox: 截图对应的屏幕区域 (x, y, w, h)。
        """
        screen_x0, screen_y0 = screen_bbox[0], screen_bbox[1]
        rects: List[SkeletonRect] = []
        for tb in text_blocks:
            xs = [pt[0] for pt in tb.bbox]
            ys = [pt[1] for pt in tb.bbox]
            left = int(min(xs))
            top = int(min(ys))
            w = max(int(max(xs)) - left, 1)
            h = max(int(max(ys)) - top, 1)
            # OCR bbox 是相对截图的，加上 screen_bbox 偏移转为屏幕坐标
            rects.append(SkeletonRect(
                screen_x=screen_x0 + left,
                screen_y=screen_y0 + top,
                w=w, h=h,
            ))
        self._skeleton_painter.set_rects(rects)
        self.show()
        self.raise_()
        self.update()

    def add_block(self, block: RenderBlock) -> None:
        """增量添加一个渲染块，移除对应骨架并触发淡入。"""
        # 移除与新块位置重叠的骨架
        self._skeleton_painter.remove_overlapping(
            block.screen_x, block.screen_y, block.width, block.height,
        )

        self._render_blocks.append(block)
        self._preview.add_text(
            block.translated_text, block.source_text,
            sort_key=block.screen_y,
        )
        if not self.isVisible():
            self.show()
            self.raise_()
        self._start_fade_in()

    def finalize_preview(self) -> None:
        """流式渲染全部完成后，按原文位置重排预览面板。"""
        self._preview.sort_by_position()

    def show_error(self, msg: str) -> None:
        """在覆盖层上显示错误提示，替换骨架屏。"""
        self._error_msg = msg
        self._skeleton_painter.clear()
        if not self.isVisible():
            self.show()
            self.raise_()
        self.update()

    def close_overlay(self) -> None:
        """关闭并隐藏覆盖层。"""
        self._render_blocks = []
        self._skeleton_painter.clear()
        self._error_msg = None
        self._preview.close_panel()
        self.hide()

    def clear(self) -> None:
        """清空渲染内容并隐藏窗口。"""
        self.close_overlay()

    # ------------------------------------------------------------------
    # 淡入动画
    # ------------------------------------------------------------------

    def _start_fade_in(self) -> None:
        """对最新添加的块触发淡入效果。"""
        # 停止上一个动画，避免多个动画争抢同一属性
        if self._fade_anim is not None:
            self._fade_anim.stop()

        self._block_opacity = 0.0
        anim = QVariantAnimation(self)
        anim.setDuration(_FADE_IN_DURATION)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.valueChanged.connect(self._on_fade_tick)
        anim.start()
        self._fade_anim = anim

    def _on_fade_tick(self, value) -> None:
        """动画每帧回调：更新透明度并重绘。"""
        self._block_opacity = float(value)
        self.update()

    # ------------------------------------------------------------------
    # Qt 事件
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            event.ignore()
        else:
            super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)

        act_copy = menu.addAction("复制全部译文")
        act_copy.triggered.connect(self._copy_all_text)

        menu.addSeparator()

        act_retranslate = menu.addAction("重新翻译")
        act_retranslate.triggered.connect(self._request_retranslate)

        act_chat = menu.addAction("智能对话")
        act_chat.triggered.connect(self._open_chat)

        menu.addSeparator()

        act_close = menu.addAction("关闭覆盖层")
        act_close.triggered.connect(self.close_overlay)

        menu.exec(event.globalPos())

    def paintEvent(self, event) -> None:  # noqa: N802
        # Space 键透视模式：不绘制任何内容，露出原文
        if self._peeking:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # ── 绘制错误提示 ──
        if self._error_msg:
            self._paint_error(painter)
            painter.end()
            return

        # ── 绘制骨架占位条（shimmer 动画） ──
        self._skeleton_painter.paint(painter)

        if not self._render_blocks:
            painter.end()
            return

        # ── 绘制已翻译的文本块 ──
        # 除最后一个块外用完整不透明度，最后一个块用动画不透明度
        n = len(self._render_blocks)
        for i, block in enumerate(self._render_blocks):
            opacity = self._block_opacity if i == n - 1 else 1.0
            self._paint_block(painter, block, opacity)

        painter.end()

    def _paint_block(
        self, painter: QPainter, block: RenderBlock, opacity: float,
    ) -> None:
        """绘制单个翻译文本块。"""
        lx = block.screen_x - self.x()
        ly = block.screen_y - self.y()

        # 背景矩形（带不透明度调制）
        bg = block.bg_color
        a = int(bg[3] * opacity)
        painter.fillRect(
            lx, ly, block.width, block.height,
            QColor(bg[0], bg[1], bg[2], a),
        )

        # 如果译文与原文完全相同（LLM 漏译 fallback），只画背景覆盖原文
        if (block.source_text
                and block.translated_text.strip() == block.source_text.strip()):
            return

        # 字体（使用检测到的字体属性，回退到默认中文字体）
        font = QFont(block.font_family or FONT_FAMILY_ZH)
        font.setPixelSize(block.font_size)
        if block.font_bold:
            font.setBold(True)
        if block.font_italic:
            font.setItalic(True)
        painter.setFont(font)

        # 文字颜色（带不透明度）
        tc = block.text_color
        painter.setPen(QColor(tc[0], tc[1], tc[2], int(255 * opacity)))

        # 根据对齐方式构建 QTextOption
        h_align = _ALIGN_MAP.get(block.alignment, Qt.AlignmentFlag.AlignLeft)
        text_opt = QTextOption(h_align | Qt.AlignmentFlag.AlignTop)
        text_opt.setWrapMode(QTextOption.WrapMode.WordWrap)

        # 绘制多行文本
        rect = QRectF(lx, ly, block.width, block.height)
        painter.drawText(rect, block.translated_text, text_opt)

    # ------------------------------------------------------------------
    # 右键菜单操作
    # ------------------------------------------------------------------

    def _copy_all_text(self) -> None:
        texts = [b.translated_text for b in self._render_blocks]
        if texts:
            QApplication.clipboard().setText("\n".join(texts))

    def _request_retranslate(self) -> None:
        bbox = (self._win_x, self._win_y, self.width(), self.height())
        self.sig_retranslate.emit(bbox)

    def _open_chat(self) -> None:
        texts = [b.translated_text for b in self._render_blocks]
        if texts:
            self.sig_open_chat.emit("\n".join(texts))

    def _sync_preview(self) -> None:
        bbox = (self.x(), self.y(), self.width(), self.height())
        self._preview.position_beside(bbox)
        self.sig_geometry_changed.emit(bbox)

    def _paint_error(self, painter: QPainter) -> None:
        """在覆盖层中央绘制错误提示条。"""
        font = QFont(FONT_FAMILY_ZH)
        font.setPixelSize(14)
        painter.setFont(font)

        text = self._error_msg or "翻译失败"
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text)
        text_h = fm.height()
        pad_x, pad_y = 16, 10

        bar_w = text_w + pad_x * 2
        bar_h = text_h + pad_y * 2
        bar_x = (self.width() - bar_w) // 2
        bar_y = (self.height() - bar_h) // 2

        painter.setBrush(_ERROR_BG)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 6, 6)

        painter.setPen(_ERROR_TEXT)
        painter.drawText(
            bar_x + pad_x, bar_y + pad_y + fm.ascent(),
            text,
        )
