"""快速互译弹窗 — 选中文本或手动输入后即时弹出翻译卡片。

支持两种模式，共用同一组件：
  - 结果模式（source_text 非空）：直接展示原文 + 流式译文
  - 输入模式（source_text 为空）：展示可编辑输入框，提交后原地切换为结果模式

职责单一：只负责 UI 渲染与用户交互；
翻译逻辑委托给 QuickTranslator；
不直接操作剪贴板或热键。
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import (
    QObject,
    QPoint,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QColor, QCursor, QFont, QKeyEvent, QPainter, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from magic_mirror.translation.quick_translator import QuickTranslator
from magic_mirror.ui.chat_theme import (
    ACCENT,
    ACCENT_DIM,
    BG_INPUT,
    BG_WINDOW,
    BORDER,
    TEXT,
    TEXT_DIM,
)

logger = logging.getLogger(__name__)

# ── 弹窗尺寸常量 ──
_POPUP_WIDTH = 420
_SOURCE_MAX_LINES = 3          # 原文区最多折叠显示行数
_CURSOR_OFFSET_X = 12          # 相对鼠标光标的水平偏移
_CURSOR_OFFSET_Y = 20          # 相对鼠标光标的垂直偏移

# ── 样式 ──
_QSS = f"""
QWidget#quickTranslatePopup {{
    background: {BG_WINDOW};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

/* 标题栏 */
QWidget#titleBar {{
    background: #1a1a1a;
    border-bottom: 1px solid {BORDER};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}}
QLabel#titleLabel {{
    color: {TEXT};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}}
QPushButton#closeBtn {{
    background: transparent;
    color: {TEXT_DIM};
    border: none;
    border-radius: 4px;
    font-size: 14px;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
}}
QPushButton#closeBtn:hover {{
    background: #c42b1c;
    color: #ffffff;
}}

/* 原文区（只读） */
QLabel#sourceLabel {{
    color: {TEXT_DIM};
    font-size: 11px;
    background: transparent;
    padding: 0px;
}}
QLabel#sourceText {{
    color: {TEXT_DIM};
    font-size: 12px;
    background: transparent;
    padding: 2px 4px;
}}
QLabel#expandHint {{
    color: #555555;
    font-size: 11px;
    background: transparent;
}}

/* 译文区 */
QLabel#resultLabel {{
    color: {TEXT_DIM};
    font-size: 11px;
    background: transparent;
    padding: 0px;
}}
QTextEdit#resultText {{
    background: transparent;
    color: {TEXT};
    border: none;
    font-size: 14px;
    padding: 2px 4px;
    selection-background-color: rgba(255,255,255,0.15);
}}

/* 分隔线 */
QWidget#separator {{
    background: {BORDER};
    min-height: 1px;
    max-height: 1px;
}}

/* 输入框（输入模式） */
QPlainTextEdit#inputBox {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: rgba(255,255,255,0.15);
}}
QPlainTextEdit#inputBox:focus {{
    border-color: {TEXT_DIM};
}}

/* 操作按钮 */
QPushButton#actionBtn {{
    background: {ACCENT_DIM};
    color: {TEXT};
    border: none;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    min-height: 26px;
}}
QPushButton#actionBtn:hover {{
    background: #505050;
}}
QPushButton#actionBtn:disabled {{
    background: #333333;
    color: #555555;
}}
QPushButton#primaryBtn {{
    background: {ACCENT};
    color: {BG_WINDOW};
    border: none;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
    min-height: 26px;
}}
QPushButton#primaryBtn:hover {{
    background: #ffffff;
}}
QPushButton#primaryBtn:disabled {{
    background: {ACCENT_DIM};
    color: {TEXT_DIM};
}}

/* 滚动条 */
QScrollBar:vertical {{
    background: transparent;
    width: 5px;
}}
QScrollBar::handle:vertical {{
    background: {ACCENT_DIM};
    border-radius: 2px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


# ------------------------------------------------------------------
# 后台翻译工作线程
# ------------------------------------------------------------------

class _TranslateWorker(QRunnable):
    """在线程池中执行流式翻译，通过信号将 token 推送给 UI。"""

    class Signals(QObject):
        token = pyqtSignal(str)     # 每个 token 片段
        finished = pyqtSignal()
        error = pyqtSignal(str)

    def __init__(self, translator: QuickTranslator, text: str) -> None:
        super().__init__()
        self.signals = self.Signals()
        self._translator = translator
        self._text = text

    def run(self) -> None:
        try:
            for token in self._translator.translate_stream(self._text):
                self.signals.token.emit(token)
            self.signals.finished.emit()
        except Exception as exc:
            logger.exception("QuickTranslator 翻译失败")
            self.signals.error.emit(str(exc))


# ------------------------------------------------------------------
# 输入框（Enter 提交，Shift+Enter 换行）
# ------------------------------------------------------------------

class _InputBox(QPlainTextEdit):
    """Enter 提交，Shift+Enter 换行的输入框。"""

    sig_submit = pyqtSignal(str)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ):
            text = self.toPlainText().strip()
            if text:
                self.sig_submit.emit(text)
            event.accept()
            return
        super().keyPressEvent(event)


# ------------------------------------------------------------------
# 快速互译弹窗
# ------------------------------------------------------------------

class QuickTranslatePopup(QWidget):
    """轻量翻译弹窗，支持结果模式和输入模式。

    信号:
        open_in_chat(str, str)   (原文, 译文) → 打开 ChatDialog 继续对话
    """

    open_in_chat = pyqtSignal(str, str)

    def __init__(self, source_text: str, translator: QuickTranslator) -> None:
        super().__init__(None)
        self._translator = translator
        self._source_text = source_text
        self._result_text = ""
        self._source_expanded = False

        # 窗口标志：无边框、始终置顶、不在任务栏显示
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("quickTranslatePopup")
        self.setStyleSheet(_QSS)
        self.setFixedWidth(_POPUP_WIDTH)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        self._build_ui()

        if source_text:
            # 有选中文本 → 直接进入结果模式（启动翻译）
            self._switch_to_result_mode(source_text)
        else:
            # 无选中文本 → 进入输入模式
            self._show_input_mode()

    # ----------------------------------------------------------------
    # UI 构建
    # ----------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 容器（用于圆角背景）
        container = QWidget()
        container.setObjectName("quickTranslatePopup")
        outer.addWidget(container)

        self._main_layout = QVBoxLayout(container)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # ── 标题栏 ──
        self._title_bar = self._make_title_bar()
        self._main_layout.addWidget(self._title_bar)

        # ── 输入模式区域 ──
        self._input_widget = self._make_input_widget()
        self._main_layout.addWidget(self._input_widget)

        # ── 结果模式区域（初始隐藏）──
        self._result_widget = self._make_result_widget()
        self._result_widget.setVisible(False)
        self._main_layout.addWidget(self._result_widget)

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(34)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(6)

        self._title_label = QLabel("快速翻译")
        self._title_label.setObjectName("titleLabel")
        layout.addWidget(self._title_label)

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding))

        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return bar

    def _make_input_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self._input_box = _InputBox()
        self._input_box.setObjectName("inputBox")
        self._input_box.setPlaceholderText("输入要翻译的文字，Enter 提交，Shift+Enter 换行...")
        self._input_box.setFixedHeight(80)
        self._input_box.sig_submit.connect(self._on_input_submitted)
        layout.addWidget(self._input_box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding))

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("actionBtn")
        cancel_btn.clicked.connect(self.close)
        btn_row.addWidget(cancel_btn)

        self._translate_btn = QPushButton("翻译 ▶")
        self._translate_btn.setObjectName("primaryBtn")
        self._translate_btn.clicked.connect(self._on_translate_btn_clicked)
        btn_row.addWidget(self._translate_btn)

        layout.addLayout(btn_row)
        return widget

    def _make_result_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(6)

        # 原文区头部
        src_header = QHBoxLayout()
        src_label = QLabel("原文")
        src_label.setObjectName("sourceLabel")
        src_header.addWidget(src_label)
        src_header.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding))

        self._expand_btn = QPushButton("展开")
        self._expand_btn.setObjectName("actionBtn")
        self._expand_btn.setFixedHeight(18)
        self._expand_btn.setFixedWidth(40)
        self._expand_btn.setVisible(False)
        self._expand_btn.clicked.connect(self._toggle_source_expand)
        src_header.addWidget(self._expand_btn)
        layout.addLayout(src_header)

        self._source_display = QLabel()
        self._source_display.setObjectName("sourceText")
        self._source_display.setWordWrap(True)
        self._source_display.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._source_display)

        # 分隔线
        sep = QWidget()
        sep.setObjectName("separator")
        layout.addWidget(sep)

        # 译文区
        result_label = QLabel("译文")
        result_label.setObjectName("resultLabel")
        layout.addWidget(result_label)

        self._result_display = QTextEdit()
        self._result_display.setObjectName("resultText")
        self._result_display.setReadOnly(True)
        self._result_display.setMinimumHeight(60)
        self._result_display.setMaximumHeight(300)
        self._result_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        layout.addWidget(self._result_display)

        # 操作按钮栏
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._copy_btn = QPushButton("复制译文")
        self._copy_btn.setObjectName("actionBtn")
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._on_copy_result)
        btn_row.addWidget(self._copy_btn)

        btn_row.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding))

        self._chat_btn = QPushButton("在聊天中继续 ▶")
        self._chat_btn.setObjectName("actionBtn")
        self._chat_btn.setEnabled(False)
        self._chat_btn.clicked.connect(self._on_open_chat)
        btn_row.addWidget(self._chat_btn)

        layout.addLayout(btn_row)
        return widget

    # ----------------------------------------------------------------
    # 模式切换
    # ----------------------------------------------------------------

    def _show_input_mode(self) -> None:
        """展示输入模式 UI，输入框自动聚焦。"""
        self._title_label.setText("快速翻译")
        self._input_widget.setVisible(True)
        self._result_widget.setVisible(False)
        self.adjustSize()
        QTimer.singleShot(50, self._input_box.setFocus)

    def _switch_to_result_mode(self, text: str) -> None:
        """切换为结果模式：隐藏输入区，展示原文，启动后台翻译线程。"""
        self._source_text = text
        self._result_text = ""

        # 切换布局
        self._input_widget.setVisible(False)
        self._result_widget.setVisible(True)
        self._title_label.setText("正在翻译...")

        # 填充原文（折叠）
        self._update_source_display()

        # 清空译文区
        self._result_display.clear()
        self._copy_btn.setEnabled(False)
        self._chat_btn.setEnabled(False)

        self.adjustSize()

        # 启动后台翻译
        worker = _TranslateWorker(self._translator, text)
        worker.signals.token.connect(self._on_token)
        worker.signals.finished.connect(self._on_translate_finished)
        worker.signals.error.connect(self._on_translate_error)
        QThreadPool.globalInstance().start(worker)

    def _update_source_display(self) -> None:
        """根据展开状态更新原文显示（折叠 / 展开）。"""
        text = self._source_text
        lines = text.splitlines()

        if self._source_expanded or len(lines) <= _SOURCE_MAX_LINES:
            display = text
            self._expand_btn.setVisible(len(lines) > _SOURCE_MAX_LINES)
            if self._source_expanded:
                self._expand_btn.setText("折叠")
        else:
            display = "\n".join(lines[:_SOURCE_MAX_LINES]) + "\n..."
            self._expand_btn.setVisible(True)
            self._expand_btn.setText("展开")

        self._source_display.setText(display)

    @pyqtSlot()
    def _toggle_source_expand(self) -> None:
        self._source_expanded = not self._source_expanded
        self._update_source_display()
        self.adjustSize()

    # ----------------------------------------------------------------
    # 槽函数
    # ----------------------------------------------------------------

    @pyqtSlot(str)
    def _on_input_submitted(self, text: str) -> None:
        self._switch_to_result_mode(text)

    @pyqtSlot()
    def _on_translate_btn_clicked(self) -> None:
        text = self._input_box.toPlainText().strip()
        if text:
            self._switch_to_result_mode(text)

    @pyqtSlot(str)
    def _on_token(self, token: str) -> None:
        """流式追加翻译 token。"""
        self._result_text += token
        cursor = self._result_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self._result_display.setTextCursor(cursor)
        # 自动滚动到底部
        self._result_display.verticalScrollBar().setValue(
            self._result_display.verticalScrollBar().maximum()
        )
        # 动态调整高度
        self._resize_result_display()

    @pyqtSlot()
    def _on_translate_finished(self) -> None:
        self._title_label.setText("翻译完成")
        self._copy_btn.setEnabled(True)
        self._chat_btn.setEnabled(True)
        logger.debug("翻译完成，共 %d 字符", len(self._result_text))

    @pyqtSlot(str)
    def _on_translate_error(self, msg: str) -> None:
        self._title_label.setText("翻译失败")
        self._result_display.setPlainText(f"[错误] {msg}")
        logger.error("翻译失败: %s", msg)

    @pyqtSlot()
    def _on_copy_result(self) -> None:
        QApplication.clipboard().setText(self._result_text)
        self._copy_btn.setText("已复制 ✓")
        QTimer.singleShot(1500, lambda: self._copy_btn.setText("复制译文"))

    @pyqtSlot()
    def _on_open_chat(self) -> None:
        self.open_in_chat.emit(self._source_text, self._result_text)
        self.close()

    # ----------------------------------------------------------------
    # 定位 & 辅助
    # ----------------------------------------------------------------

    def show_near_cursor(self) -> None:
        """在鼠标光标右下方弹出，自动避开屏幕边缘。"""
        self.adjustSize()

        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()

        x = cursor_pos.x() + _CURSOR_OFFSET_X
        y = cursor_pos.y() + _CURSOR_OFFSET_Y

        # 右边界检查
        if x + self.width() > geo.right():
            x = cursor_pos.x() - self.width() - _CURSOR_OFFSET_X
        # 下边界检查
        if y + self.height() > geo.bottom():
            y = cursor_pos.y() - self.height() - _CURSOR_OFFSET_Y

        # 确保在屏幕内
        x = max(geo.left(), min(x, geo.right() - self.width()))
        y = max(geo.top(), min(y, geo.bottom() - self.height()))

        self.move(x, y)
        self.show()
        self._fade_in()

    def _fade_in(self) -> None:
        """200ms 淡入动效。"""
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _resize_result_display(self) -> None:
        """根据内容动态调整译文区高度（60~300px）。"""
        doc = self._result_display.document()
        content_height = int(doc.size().height()) + 8
        clamped = max(60, min(content_height, 300))
        if self._result_display.height() != clamped:
            self._result_display.setFixedHeight(clamped)
            self.adjustSize()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        """点击标题栏可拖拽移动弹窗。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and hasattr(self, "_drag_pos")
        ):
            # 仅在标题栏区域允许拖拽
            if event.position().y() <= 34:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)
