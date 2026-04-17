"""聊天对话框 — 基于提取文本的多轮对话 UI。

职责单一：只负责聊天界面的展示与用户交互，
聊天逻辑委托给 ChatSession，模型管理委托给 model_service。
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from magic_mirror.chat.chat_service import ChatSession
from magic_mirror.chat.model_service import (
    list_models,
    load_selected_model,
    save_selected_model,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 后台工作线程
# ------------------------------------------------------------------

class _ModelListWorker(QRunnable):
    """后台加载可用模型列表。"""

    class Signals(QObject):
        finished = pyqtSignal(list)  # List[str]

    def __init__(self) -> None:
        super().__init__()
        self.signals = self.Signals()

    def run(self) -> None:
        models = list_models()
        self.signals.finished.emit(models)


class _ChatStreamWorker(QRunnable):
    """后台流式发送聊天消息。"""

    class Signals(QObject):
        chunk = pyqtSignal(str)       # 流式文本片段
        finished = pyqtSignal()
        error = pyqtSignal(str)

    def __init__(self, session: ChatSession, user_input: str) -> None:
        super().__init__()
        self.signals = self.Signals()
        self._session = session
        self._user_input = user_input

    def run(self) -> None:
        try:
            for piece in self._session.send_stream(self._user_input):
                self.signals.chunk.emit(piece)
            self.signals.finished.emit()
        except Exception as exc:
            self.signals.error.emit(str(exc))


# ------------------------------------------------------------------
# 聊天对话框
# ------------------------------------------------------------------

class ChatDialog(QDialog):
    """多轮对话窗口 — 基于 OCR 提取文本与 LLM 交互。"""

    def __init__(
        self,
        context_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Magic Mirror — 智能对话")
        self.setMinimumSize(600, 500)
        self.resize(700, 550)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self._context_text = context_text
        self._session: ChatSession | None = None
        self._streaming = False

        self._init_ui()
        self._load_models()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ── 顶部：模型选择 ──
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("模型:"))
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(250)
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        top_bar.addWidget(self._model_combo, 1)

        self._token_label = QLabel("Token: ~0")
        self._token_label.setStyleSheet("color: gray; font-size: 11px;")
        top_bar.addWidget(self._token_label)

        layout.addLayout(top_bar)

        # ── 中部：对话区 + 原文区（可折叠） ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 对话显示
        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setFont(QFont("Microsoft YaHei", 10))
        splitter.addWidget(self._chat_display)

        # 原文参考面板
        context_panel = QWidget()
        ctx_layout = QVBoxLayout(context_panel)
        ctx_layout.setContentsMargins(0, 0, 0, 0)
        ctx_label = QLabel("原文参考")
        ctx_label.setStyleSheet("font-weight: bold; font-size: 11px; color: gray;")
        ctx_layout.addWidget(ctx_label)
        self._context_display = QPlainTextEdit()
        self._context_display.setReadOnly(True)
        self._context_display.setPlainText(self._context_text)
        self._context_display.setFont(QFont("Consolas", 9))
        ctx_layout.addWidget(self._context_display)
        splitter.addWidget(context_panel)

        splitter.setSizes([500, 200])
        layout.addWidget(splitter, 1)

        # ── 底部：输入区 ──
        input_bar = QHBoxLayout()
        self._input_edit = _ChatInputEdit()
        self._input_edit.sig_submit.connect(self._on_send)
        self._input_edit.setPlaceholderText("输入问题，Enter 发送，Shift+Enter 换行...")
        self._input_edit.setMaximumHeight(80)
        self._input_edit.setFont(QFont("Microsoft YaHei", 10))
        input_bar.addWidget(self._input_edit, 1)

        btn_layout = QVBoxLayout()
        self._send_btn = QPushButton("发送")
        self._send_btn.clicked.connect(self._on_send)
        btn_layout.addWidget(self._send_btn)

        self._clear_btn = QPushButton("清空")
        self._clear_btn.clicked.connect(self._on_clear)
        btn_layout.addWidget(self._clear_btn)
        input_bar.addLayout(btn_layout)

        layout.addLayout(input_bar)

    # ------------------------------------------------------------------
    # 模型加载
    # ------------------------------------------------------------------

    def _load_models(self) -> None:
        """后台加载模型列表。"""
        self._model_combo.clear()
        self._model_combo.addItem("加载中...")
        self._model_combo.setEnabled(False)

        worker = _ModelListWorker()
        worker.signals.finished.connect(self._on_models_loaded)
        QThreadPool.globalInstance().start(worker)

    @pyqtSlot(list)
    def _on_models_loaded(self, models: List[str]) -> None:
        """模型列表加载完成。"""
        self._model_combo.clear()
        self._model_combo.setEnabled(True)

        if not models:
            self._model_combo.addItem("(无可用模型)")
            return

        self._model_combo.addItems(models)

        # 恢复持久化的选择
        saved = load_selected_model()
        if saved and saved in models:
            self._model_combo.setCurrentText(saved)
        
        self._init_session()

    def _on_model_changed(self, model_name: str) -> None:
        """用户切换模型 → 持久化 + 更新会话。"""
        if not model_name or model_name in ("加载中...", "(无可用模型)"):
            return
        save_selected_model(model_name)
        if self._session is not None:
            self._session.model = model_name
            logger.info("切换聊天模型: %s", model_name)

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------

    def _init_session(self) -> None:
        """根据当前选中模型创建聊天会话。"""
        model = self._model_combo.currentText()
        if not model or model in ("加载中...", "(无可用模型)"):
            return
        self._session = ChatSession(self._context_text, model)
        self._update_token_label()

    # ------------------------------------------------------------------
    # 聊天交互
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_send(self) -> None:
        """发送用户消息。"""
        if self._streaming:
            return
        text = self._input_edit.toPlainText().strip()
        if not text:
            return
        if self._session is None:
            self._init_session()
        if self._session is None:
            return

        self._input_edit.clear()
        self._append_message("user", text)

        self._streaming = True
        self._send_btn.setEnabled(False)
        self._append_message("assistant", "", start=True)

        worker = _ChatStreamWorker(self._session, text)
        worker.signals.chunk.connect(self._on_stream_chunk)
        worker.signals.finished.connect(self._on_stream_done)
        worker.signals.error.connect(self._on_stream_error)
        QThreadPool.globalInstance().start(worker)

    @pyqtSlot(str)
    def _on_stream_chunk(self, text: str) -> None:
        """流式接收文本片段，追加到对话区。"""
        cursor = self._chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self._chat_display.setTextCursor(cursor)
        self._chat_display.ensureCursorVisible()

    @pyqtSlot()
    def _on_stream_done(self) -> None:
        """流式响应完成。"""
        self._streaming = False
        self._send_btn.setEnabled(True)
        self._update_token_label()
        self._input_edit.setFocus()

    @pyqtSlot(str)
    def _on_stream_error(self, msg: str) -> None:
        """流式响应出错。"""
        self._streaming = False
        self._send_btn.setEnabled(True)
        self._append_message("system", f"[错误] {msg}")
        self._update_token_label()

    @pyqtSlot()
    def _on_clear(self) -> None:
        """清空对话历史。"""
        if self._session:
            self._session.clear_history()
        self._chat_display.clear()
        self._update_token_label()

    # ------------------------------------------------------------------
    # 显示辅助
    # ------------------------------------------------------------------

    def _append_message(self, role: str, text: str, start: bool = False) -> None:
        """向对话区追加一条消息。"""
        color_map = {"user": "#0066cc", "assistant": "#333333", "system": "#cc0000"}
        label_map = {"user": "你", "assistant": "AI", "system": "系统"}
        color = color_map.get(role, "#333")
        label = label_map.get(role, role)

        cursor = self._chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)

        if start:
            # 流式开始：只写标签，内容由 chunk 追加
            cursor.insertHtml(
                f'<p><b style="color:{color}">{label}:</b> '
            )
        else:
            cursor.insertHtml(
                f'<p><b style="color:{color}">{label}:</b> '
                f'{text.replace(chr(10), "<br>")}</p><br>'
            )
        self._chat_display.setTextCursor(cursor)
        self._chat_display.ensureCursorVisible()

    def _update_token_label(self) -> None:
        """更新 token 估算显示。"""
        if self._session:
            tokens = self._session.estimate_tokens()
            self._token_label.setText(f"Token: ~{tokens}")
        else:
            self._token_label.setText("Token: ~0")


# ------------------------------------------------------------------
# 自定义输入框 — Enter 发送, Shift+Enter 换行
# ------------------------------------------------------------------

class _ChatInputEdit(QPlainTextEdit):
    """Enter 发送消息，Shift+Enter 换行的输入框。"""

    sig_submit = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sig_submit.emit()
        else:
            super().keyPressEvent(event)
