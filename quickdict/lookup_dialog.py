"""
lookup_dialog.py -- 双语互查输入对话框。

职责单一：提供输入框 + 结果列表 UI，接收用户中英文输入并展示查询结果。
不含数据库查询逻辑（通过信号与外部引擎交互）。
"""
import os

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QKeyEvent, QPixmap, QPainter
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from quickdict.config import ASSETS_DIR, STYLES_DIR


def _load_dialog_qss() -> str:
    qss_path = os.path.join(STYLES_DIR, "lookup_dialog.qss")
    if os.path.exists(qss_path):
        with open(qss_path, encoding="utf-8") as f:
            return f.read()
    return ""


class LookupDialog(QDialog):
    """双语互查输入对话框。"""

    sig_search_requested = pyqtSignal(str)  # 用户请求搜索关键词
    sig_detail_requested = pyqtSignal(str)  # 用户点击某词条，请求完整释义

    _DEBOUNCE_MS = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_window()
        self._init_ui()
        self._apply_style()
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(self._DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._on_debounce_fire)

    def _init_window(self):
        self.setWindowTitle("双语互查")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setWindowIcon(self._load_icon())
        self.setMinimumSize(420, 320)
        self.resize(480, 500)

    @staticmethod
    def _load_icon() -> QIcon:
        icon_path = os.path.join(ASSETS_DIR, "icon.png")
        if os.path.isfile(icon_path):
            return QIcon(icon_path)
        # 回退：绘制一个简单图标
        pm = QPixmap(64, 64)
        pm.fill(QColor(67, 97, 238))
        p = QPainter(pm)
        p.setPen(QColor(255, 255, 255))
        from PyQt6.QtGui import QFont as _QF
        p.setFont(_QF("Segoe UI", 36, _QF.Weight.Bold))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "词")
        p.end()
        return QIcon(pm)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # ── 标题行 ──
        title = QLabel("🔍 双语互查")
        title.setObjectName("dialog_title")
        layout.addWidget(title)

        # ── 输入行：输入框 + 查询按钮 ──
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = QLineEdit()
        self._input.setObjectName("search_input")
        self._input.setPlaceholderText("输入中文或英文关键词…")
        self._input.returnPressed.connect(self._on_search)
        self._input.textChanged.connect(self._on_text_changed)
        input_row.addWidget(self._input)

        self._btn_search = QPushButton("查询")
        self._btn_search.setObjectName("search_btn")
        self._btn_search.clicked.connect(self._on_search)
        self._btn_search.setFixedWidth(60)
        input_row.addWidget(self._btn_search)

        layout.addLayout(input_row)

        # ── 结果计数 ──
        self._lbl_count = QLabel("")
        self._lbl_count.setObjectName("result_count")
        layout.addWidget(self._lbl_count)

        # ── 结果滚动区域 ──
        self._scroll = QScrollArea()
        self._scroll.setObjectName("result_scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._result_container = QWidget()
        self._result_layout = QVBoxLayout(self._result_container)
        self._result_layout.setContentsMargins(0, 0, 0, 0)
        self._result_layout.setSpacing(4)
        self._result_layout.addStretch()

        self._scroll.setWidget(self._result_container)
        layout.addWidget(self._scroll)

    def _apply_style(self):
        qss = _load_dialog_qss()
        if qss:
            self.setStyleSheet(qss)
        else:
            self.setStyleSheet(self._default_style())

    @staticmethod
    def _default_style() -> str:
        return """
            QDialog {
                background-color: #FFFFFF;
            }
            QLabel#dialog_title {
                font-family: "Microsoft YaHei UI", sans-serif;
                font-size: 16px;
                font-weight: 700;
                color: #1A1A2E;
            }
            QLineEdit#search_input {
                font-family: "Microsoft YaHei UI", sans-serif;
                font-size: 14px;
                padding: 6px 10px;
                border: 1px solid #D0D0D0;
                border-radius: 6px;
                background-color: #FAFAFA;
            }
            QLineEdit#search_input:focus {
                border-color: #4361EE;
                background-color: #FFFFFF;
            }
            QPushButton#search_btn {
                font-family: "Microsoft YaHei UI", sans-serif;
                font-size: 13px;
                padding: 6px 12px;
                border: none;
                border-radius: 6px;
                background-color: #4361EE;
                color: #FFFFFF;
            }
            QPushButton#search_btn:hover {
                background-color: #3451DE;
            }
            QPushButton#search_btn:pressed {
                background-color: #2A41BE;
            }
            QLabel#result_count {
                font-family: "Microsoft YaHei UI", sans-serif;
                font-size: 12px;
                color: #9E9E9E;
            }
            QFrame#result_item {
                background-color: #F9F9FB;
                border: 1px solid #EEEEEE;
                border-radius: 6px;
                padding: 8px 10px;
            }
            QFrame#result_item:hover {
                background-color: #EEF0FF;
                border-color: #4361EE;
            }
            QLabel#item_word {
                font-family: "Segoe UI", "Inter", sans-serif;
                font-size: 15px;
                font-weight: 600;
                color: #1A1A2E;
            }
            QLabel#item_phonetic {
                font-family: "Segoe UI", sans-serif;
                font-size: 12px;
                color: #6C757D;
                padding-left: 4px;
            }
            QLabel#item_collins {
                font-size: 12px;
                color: #F5A623;
            }
            QLabel#item_translation {
                font-family: "Microsoft YaHei UI", sans-serif;
                font-size: 13px;
                color: #444444;
            }
        """

    # ── 公开接口 ──────────────────────────────────────────

    def show_and_focus(self):
        """显示对话框并聚焦输入框。"""
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()
        self._input.selectAll()

    def set_busy(self, busy: bool):
        """设置搜索忙碌状态，更新按钮文本。"""
        self._btn_search.setEnabled(not busy)
        self._btn_search.setText("查询中…" if busy else "查询")
        if busy:
            self._lbl_count.setText("正在搜索…")

    def show_results(self, results: list[dict]):
        """展示搜索结果列表。"""
        self._clear_results()
        if not results:
            self._lbl_count.setText("未找到匹配结果")
            return
        self._lbl_count.setText(f"匹配结果 ({len(results)})")
        for i, item in enumerate(results, 1):
            widget = self._make_result_item(i, item)
            # 插入到 stretch 之前
            self._result_layout.insertWidget(
                self._result_layout.count() - 1, widget
            )

    def clear(self):
        """清空输入和结果。"""
        self._input.clear()
        self._clear_results()
        self._lbl_count.setText("")

    # ── 内部逻辑 ──────────────────────────────────────────

    def _on_search(self):
        """用户按 Enter 或点击查询按钮。"""
        self._debounce_timer.stop()
        keyword = self._input.text().strip()
        if keyword:
            self.sig_search_requested.emit(keyword)

    def _on_text_changed(self, text: str):
        """输入变化 → 防抖后自动搜索。"""
        self._debounce_timer.stop()
        if text.strip():
            self._debounce_timer.start()

    def _on_debounce_fire(self):
        """防抖定时器到期 → 触发搜索。"""
        keyword = self._input.text().strip()
        if keyword:
            self.sig_search_requested.emit(keyword)

    def _clear_results(self):
        """移除所有结果条目 widget。"""
        while self._result_layout.count() > 1:  # 保留末尾 stretch
            item = self._result_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _make_result_item(self, index: int, data: dict) -> QFrame:
        """构建单个结果条目 widget。"""
        frame = QFrame()
        frame.setObjectName("result_item")
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setProperty("word", data["word"])

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        # 顶部行：单词 + 音标 + 星级
        top_row = QHBoxLayout()
        top_row.setSpacing(0)

        lbl_word = QLabel(data["word"])
        lbl_word.setObjectName("item_word")
        top_row.addWidget(lbl_word)

        phonetic = data.get("phonetic", "")
        if phonetic:
            if not phonetic.startswith("/"):
                phonetic = f"/{phonetic}/"
            lbl_phonetic = QLabel(phonetic)
            lbl_phonetic.setObjectName("item_phonetic")
            top_row.addWidget(lbl_phonetic)

        top_row.addStretch()

        collins = int(data.get("collins", 0))
        if collins > 0:
            stars = "★" * collins + "☆" * (5 - collins)
            lbl_collins = QLabel(stars)
            lbl_collins.setObjectName("item_collins")
            top_row.addWidget(lbl_collins)

        layout.addLayout(top_row)

        # 中文释义（截取第一行）
        translation = data.get("translation", "")
        if translation:
            translation = translation.replace("\\n", "\n")
            first_line = translation.split("\n")[0]
            if len(first_line) > 60:
                first_line = first_line[:60] + "…"
            lbl_trans = QLabel(first_line)
            lbl_trans.setObjectName("item_translation")
            lbl_trans.setWordWrap(True)
            layout.addWidget(lbl_trans)

        # 点击事件（通过 mousePressEvent）
        frame.mousePressEvent = lambda e, w=data["word"]: self._on_item_clicked(w)

        return frame

    def _on_item_clicked(self, word: str):
        """结果条目被点击 → 发射详情请求信号。"""
        self.sig_detail_requested.emit(word)

    def keyPressEvent(self, event: QKeyEvent):
        """Esc 关闭对话框。"""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
