"""聊天对话框 — Claude Code 风格多轮对话 UI。

职责单一：只负责聊天界面的构建与用户交互，
视觉主题委托给 chat_theme，内容渲染委托给 md_renderer，
聊天逻辑委托给 ChatSession，模型管理委托给 model_service。
"""

from __future__ import annotations

import logging
from typing import List

from PyQt6.QtCore import QObject, QPoint, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from magic_mirror.chat.chat_service import ChatSession
from magic_mirror.chat.model_service import (
    list_models,
    load_selected_model,
    save_selected_model,
)
from magic_mirror.ui.chat_html_view import ChatHtmlView
from magic_mirror.ui.chat_theme import CHAT_DIALOG_QSS
from magic_mirror.ui.md_renderer import build_messages_html

logger = logging.getLogger(__name__)






# ------------------------------------------------------------------
# 后台工作线程
# ------------------------------------------------------------------

class _ModelListWorker(QRunnable):
    """后台加载可用模型列表。"""

    class Signals(QObject):
        finished = pyqtSignal(list)

    def __init__(self) -> None:
        super().__init__()
        self.signals = self.Signals()

    def run(self) -> None:
        self.signals.finished.emit(list_models())


class _ChatStreamWorker(QRunnable):
    """后台流式发送聊天消息。"""

    class Signals(QObject):
        chunk = pyqtSignal(str)
        finished = pyqtSignal()
        error = pyqtSignal(str)

    def __init__(self, session: ChatSession, user_input: str) -> None:
        super().__init__()
        self.signals = self.Signals()
        self._session = session
        self._input = user_input

    def run(self) -> None:
        try:
            for piece in self._session.send_stream(self._input):
                self.signals.chunk.emit(piece)
            self.signals.finished.emit()
        except Exception as exc:
            self.signals.error.emit(str(exc))


# ------------------------------------------------------------------
# ChatDialog
# ------------------------------------------------------------------

class ChatDialog(QDialog):
    """Claude Code 风格多轮对话窗口。"""

    def __init__(self, context_text: str, parent: QWidget | None = None,
                 prefill: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Magic Mirror Chat")
        self.setMinimumSize(700, 540)
        self.resize(820, 640)
        self._prefill = prefill
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setStyleSheet(CHAT_DIALOG_QSS)

        self._context_text = context_text
        self._session: ChatSession | None = None
        self._streaming = False

        # 消息列表：[{"role": ..., "text": ...}, ...]
        self._messages: List[dict] = []
        # 流式累积文本
        self._stream_buf = ""
        # 防抖定时器（流式渲染）
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(80)
        self._render_timer.timeout.connect(self._render_all)

        self._build_ui()
        self._load_models()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 自定义标题栏（合并品牌 + 模型选择 + 窗口控制）──
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(42)
        tbl = QHBoxLayout(title_bar)
        tbl.setContentsMargins(12, 0, 4, 0)
        tbl.setSpacing(8)

        title_icon = QLabel("●")
        title_icon.setObjectName("titleIcon")
        tbl.addWidget(title_icon)

        title_label = QLabel("Magic Mirror")
        title_label.setObjectName("titleBarLabel")
        tbl.addWidget(title_label)

        tbl.addStretch()

        self._combo = QComboBox()
        self._combo.setMinimumWidth(180)
        self._combo.currentTextChanged.connect(self._on_model_changed)
        tbl.addWidget(self._combo)

        self._token_badge = QLabel("0 tok")
        self._token_badge.setObjectName("tokenBadge")
        tbl.addWidget(self._token_badge)

        # 间隔
        spacer = QWidget()
        spacer.setFixedWidth(8)
        spacer.setStyleSheet("background:transparent;")
        tbl.addWidget(spacer)

        btn_min = QPushButton("─")
        btn_min.setObjectName("titleBtnMin")
        btn_min.setFixedSize(32, 28)
        btn_min.clicked.connect(self.showMinimized)
        tbl.addWidget(btn_min)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("titleBtnClose")
        btn_close.setFixedSize(32, 28)
        btn_close.clicked.connect(self.close)
        tbl.addWidget(btn_close)

        # 拖拽支持
        self._drag_pos: QPoint | None = None
        title_bar.mousePressEvent = self._title_mouse_press
        title_bar.mouseMoveEvent = self._title_mouse_move
        title_bar.mouseReleaseEvent = self._title_mouse_release

        root.addWidget(title_bar)

        # ── 对话区（全宽，无侧栏）──
        self._chat = ChatHtmlView()
        root.addWidget(self._chat, 1)

        # ── 底部输入栏 ──
        input_bar = QWidget()
        input_bar.setObjectName("inputBar")
        il = QHBoxLayout(input_bar)
        il.setContentsMargins(0, 8, 0, 12)
        il.setSpacing(0)

        # 居中容器
        il.addStretch(1)
        center = QHBoxLayout()
        center.setSpacing(8)
        center.setContentsMargins(0, 0, 0, 0)

        self._input = _ChatInputEdit()
        self._input.setObjectName("inputBox")
        self._input.sig_submit.connect(self._send)
        self._input.setPlaceholderText("输入消息...")
        self._input.setMaximumHeight(68)
        self._input.setMinimumWidth(500)
        self._input.setFont(QFont("Microsoft YaHei", 10))
        if self._prefill:
            self._input.setPlainText(self._prefill)
        center.addWidget(self._input)

        self._send_btn = QPushButton("↑")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.clicked.connect(self._send)
        center.addWidget(self._send_btn, 0, Qt.AlignmentFlag.AlignBottom)

        il.addLayout(center)
        il.addStretch(1)

        root.addWidget(input_bar)

        # ── 右下角拖拽调整大小 ──
        grip = QSizeGrip(self)
        grip.setObjectName("sizeGrip")
        grip.setFixedSize(12, 12)

    # ------------------------------------------------------------------
    # 标题栏拖拽
    # ------------------------------------------------------------------

    def _title_mouse_press(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _title_mouse_move(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _title_mouse_release(self, event) -> None:
        self._drag_pos = None

    # ------------------------------------------------------------------
    # 模型
    # ------------------------------------------------------------------

    def _load_models(self) -> None:
        self._combo.clear()
        self._combo.addItem("Loading…")
        self._combo.setEnabled(False)
        w = _ModelListWorker()
        w.signals.finished.connect(self._on_models_loaded)
        QThreadPool.globalInstance().start(w)

    @pyqtSlot(list)
    def _on_models_loaded(self, models: list) -> None:
        self._combo.clear()
        self._combo.setEnabled(True)
        if not models:
            self._combo.addItem("(no models)")
            return
        self._combo.addItems(models)
        saved = load_selected_model()
        if saved and saved in models:
            self._combo.setCurrentText(saved)
        self._init_session()

    def _on_model_changed(self, name: str) -> None:
        if not name or name in ("Loading…", "(no models)"):
            return
        save_selected_model(name)
        if self._session:
            self._session.model = name

    def _init_session(self) -> None:
        model = self._combo.currentText()
        if not model or model in ("Loading…", "(no models)"):
            return
        self._session = ChatSession(self._context_text, model)
        self._update_tokens()

    # ------------------------------------------------------------------
    # 发送 / 流式接收
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _send(self) -> None:
        if self._streaming:
            return
        text = self._input.toPlainText().strip()
        if not text or not self._session:
            if not self._session:
                self._init_session()
            if not text:
                return

        self._input.clear()
        self._messages.append({"role": "human", "text": text})
        self._messages.append({"role": "assistant", "text": ""})
        self._stream_buf = ""
        self._render_all()

        self._streaming = True
        self._send_btn.setEnabled(False)

        w = _ChatStreamWorker(self._session, text)
        w.signals.chunk.connect(self._on_chunk)
        w.signals.finished.connect(self._on_done)
        w.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(w)

    @pyqtSlot(str)
    def _on_chunk(self, piece: str) -> None:
        # logger.debug("[LLM chunk] %r", piece)
        self._stream_buf += piece
        self._messages[-1]["text"] = self._stream_buf
        # 防抖：不是每个 chunk 都渲染，80ms 合并一次
        if not self._render_timer.isActive():
            self._render_timer.start()

    @pyqtSlot()
    def _on_done(self) -> None:
        self._streaming = False
        self._send_btn.setEnabled(True)
        self._render_timer.stop()
        self._render_all()
        self._update_tokens()
        self._input.setFocus()

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._streaming = False
        self._send_btn.setEnabled(True)
        self._messages.append({"role": "error", "text": msg})
        self._render_timer.stop()
        self._render_all()
        self._update_tokens()

    @pyqtSlot()
    def _clear(self) -> None:
        if self._session:
            self._session.clear_history()
        self._messages.clear()
        self._chat.clear_view()
        self._update_tokens()

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def _render_all(self) -> None:
        """将所有消息渲染为 HTML 并更新 chat view。"""
        body_html = build_messages_html(
            self._messages, streaming=self._streaming,
        )
        self._chat.set_messages_html(body_html)

    def _update_tokens(self) -> None:
        if self._session:
            t = self._session.estimate_tokens()
            self._token_badge.setText(f"{t} tok")
        else:
            self._token_badge.setText("0 tok")


# ------------------------------------------------------------------
# Enter = 发送，Shift+Enter = 换行
# ------------------------------------------------------------------

class _ChatInputEdit(QPlainTextEdit):
    sig_submit = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sig_submit.emit()
        else:
            super().keyPressEvent(event)
