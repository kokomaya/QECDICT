"""
popup_widget.py — 翻译弹窗 UI 组件。

职责单一：接收格式化的词典数据，在指定坐标展示美观的翻译卡片。
不包含查询逻辑或取词逻辑。
"""
import os

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QCursor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from quickdict._formatter import EXCHANGE_TYPE_MAP
from quickdict.config import STYLES_DIR

_MAX_LINES = 3  # 释义最多显示行数


def _load_qss() -> str:
    qss_path = os.path.join(STYLES_DIR, "popup.qss")
    if os.path.exists(qss_path):
        with open(qss_path, encoding="utf-8") as f:
            return f.read()
    return ""


def _truncate_lines(text: str, max_lines: int = _MAX_LINES) -> str:
    """截断多行文本，超出部分显示省略号。返回 HTML（用 <br> 换行）。"""
    if not text:
        return ""
    # 数据库中存储的是字面 "\\n"，需先替换为真实换行再处理
    text = text.replace("\\n", "\n")
    lines = text.strip().split("\n")
    if len(lines) <= max_lines:
        return "<br>".join(lines)
    return "<br>".join(lines[:max_lines]) + "<br>..."


def _format_exchange_display(exchange: dict[str, str]) -> str:
    """将 exchange 字典格式化为可读字符串。"""
    if not exchange:
        return ""
    parts = []
    for typ, form in exchange.items():
        label = EXCHANGE_TYPE_MAP.get(typ, typ)
        parts.append(f"{label}: {form}")
    return "  ".join(parts)


# ── 分隔线工厂 ────────────────────────────────────────────

def _make_separator() -> QFrame:
    line = QFrame()
    line.setObjectName("separator")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    return line


# ══════════════════════════════════════════════════════════
#  PopupWidget
# ══════════════════════════════════════════════════════════

class PopupWidget(QWidget):
    """翻译弹窗：圆角卡片 + 淡入上滑动画 + 智能定位。"""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_window()
        self._init_ui()
        self._init_shadow()
        self.setStyleSheet(_load_qss())
        self._anim_group: QParallelAnimationGroup | None = None

    # ── 初始化 ────────────────────────────────────────────

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("QECDict")
        self.setMaximumWidth(420)
        self.setMinimumWidth(280)

    def _init_ui(self):
        # 最外层布局（透明背景，留出阴影空间）
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        # 卡片容器
        self._card = QFrame()
        self._card.setObjectName("card")
        outer.addWidget(self._card)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(6)

        # ── 顶部行：单词 + 音标 + 星级 ──
        top_row = QHBoxLayout()
        top_row.setSpacing(0)

        self._lbl_word = QLabel()
        self._lbl_word.setObjectName("word")
        top_row.addWidget(self._lbl_word)

        self._lbl_phonetic = QLabel()
        self._lbl_phonetic.setObjectName("phonetic")
        top_row.addWidget(self._lbl_phonetic)

        top_row.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )

        self._lbl_collins = QLabel()
        self._lbl_collins.setObjectName("collins")
        top_row.addWidget(self._lbl_collins)

        layout.addLayout(top_row)

        # Lemma 提示（仅词形还原时显示）
        self._lbl_lemma = QLabel()
        self._lbl_lemma.setObjectName("lemma_hint")
        self._lbl_lemma.setVisible(False)
        layout.addWidget(self._lbl_lemma)

        # ── 分隔线 1 ──
        layout.addWidget(_make_separator())

        # ── 中部：释义 ──
        self._lbl_translation = QLabel()
        self._lbl_translation.setObjectName("translation")
        self._lbl_translation.setWordWrap(True)
        layout.addWidget(self._lbl_translation)

        self._lbl_definition = QLabel()
        self._lbl_definition.setObjectName("definition")
        self._lbl_definition.setWordWrap(True)
        layout.addWidget(self._lbl_definition)

        # ── 分隔线 2 ──
        self._sep2 = _make_separator()
        layout.addWidget(self._sep2)

        # ── 底部行：词频 | 标签 | 词形变化 ──
        self._lbl_freq = QLabel()
        self._lbl_freq.setObjectName("freq_info")
        layout.addWidget(self._lbl_freq)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        self._lbl_tags = QLabel()
        self._lbl_tags.setObjectName("tags")
        bottom_row.addWidget(self._lbl_tags)

        bottom_row.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )

        self._lbl_exchange = QLabel()
        self._lbl_exchange.setObjectName("exchange_info")
        self._lbl_exchange.setWordWrap(True)
        bottom_row.addWidget(self._lbl_exchange)

        layout.addLayout(bottom_row)

    def _init_shadow(self):
        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 35))
        shadow.setOffset(0, 4)
        self._card.setGraphicsEffect(shadow)

    # ── 公开接口 ──────────────────────────────────────────

    def show_word(self, data: dict, x: int, y: int):
        """在指定坐标附近显示翻译弹窗。"""
        self._update_content(data)
        self.adjustSize()

        fx, fy = self._adjust_position(x, y)
        self.move(fx, fy)

        self.setWindowOpacity(0.0)
        self.show()
        self.activateWindow()
        self._animate_show(fx, fy)

    def hide_popup(self):
        """隐藏弹窗。"""
        self.hide()
        self.closed.emit()

    # ── 内容更新 ──────────────────────────────────────────

    def _update_content(self, data: dict):
        self._lbl_word.setText(data.get("word", ""))
        self._lbl_phonetic.setText(data.get("phonetic", ""))

        collins = data.get("collins_display", "")
        self._lbl_collins.setText(collins)
        self._lbl_collins.setVisible(bool(collins))

        # Lemma 提示
        if data.get("is_lemma_result") and data.get("original_word"):
            self._lbl_lemma.setText(f"← 由 \"{data['original_word']}\" 词形还原")
            self._lbl_lemma.setVisible(True)
        else:
            self._lbl_lemma.setVisible(False)

        # 释义
        translation = _truncate_lines(data.get("translation", ""))
        self._lbl_translation.setText(translation)
        self._lbl_translation.setVisible(bool(translation))

        definition = _truncate_lines(data.get("definition", ""))
        self._lbl_definition.setText(definition)
        self._lbl_definition.setVisible(bool(definition))

        # 底部信息
        freq_parts = []
        bnc = data.get("bnc", 0)
        frq = data.get("frq", 0)
        if bnc:
            freq_parts.append(f"BNC: {bnc}")
        if frq:
            freq_parts.append(f"当代: {frq}")
        if data.get("oxford"):
            freq_parts.append("牛津核心")
        freq_text = "  |  ".join(freq_parts)
        self._lbl_freq.setText(freq_text)
        self._lbl_freq.setVisible(bool(freq_text))

        tag_display = data.get("tag_display", "")
        self._lbl_tags.setText(tag_display)
        self._lbl_tags.setVisible(bool(tag_display))

        exchange_text = _format_exchange_display(data.get("exchange", {}))
        self._lbl_exchange.setText(exchange_text)
        self._lbl_exchange.setVisible(bool(exchange_text))

        # 底部全空时隐藏分隔线
        has_bottom = bool(freq_text or tag_display or exchange_text)
        self._sep2.setVisible(has_bottom)

    # ── 智能定位 ──────────────────────────────────────────

    def _adjust_position(self, x: int, y: int) -> tuple[int, int]:
        """确保弹窗不超出屏幕。"""
        screen = QApplication.screenAt(QPoint(x, y))
        if screen is None:
            screen = QApplication.primaryScreen()
        sr = screen.availableGeometry()

        pw = self.sizeHint().width()
        ph = self.sizeHint().height()

        # 默认：鼠标右下方
        fx = x + 16
        fy = y + 20

        # 右溢出 → 鼠标左侧
        if fx + pw > sr.right():
            fx = x - pw - 8

        # 下溢出 → 鼠标上方
        if fy + ph > sr.bottom():
            fy = y - ph - 8

        fx = max(sr.left(), fx)
        fy = max(sr.top(), fy)
        return fx, fy

    # ── 动画 ──────────────────────────────────────────────

    def _animate_show(self, target_x: int, target_y: int):
        # 淡入
        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setDuration(150)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 上滑（从下方 8px 处滑入）
        start_pos = QPoint(target_x, target_y + 8)
        end_pos = QPoint(target_x, target_y)
        self.move(start_pos)

        slide = QPropertyAnimation(self, b"pos")
        slide.setDuration(150)
        slide.setStartValue(start_pos)
        slide.setEndValue(end_pos)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(fade)
        self._anim_group.addAnimation(slide)
        self._anim_group.start()

    # ── 事件处理 ──────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide_popup()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self.hide_popup()
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        # 允许点击弹窗内部（不关闭），外部点击由 focusOut 处理
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════
#  LoadingDot — 取词进度指示
# ══════════════════════════════════════════════════════════

class LoadingDot(QWidget):
    """鼠标旁的极简加载指示：小圆点 + 脉冲动画。"""

    _SIZE = 10        # 圆点直径（px）
    _WINDOW = 22      # 窗口尺寸（留阴影空间）
    _COLOR = QColor(67, 97, 238, 200)  # 蓝色半透明

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self._WINDOW, self._WINDOW)

        # 脉冲动画：透明度 0.4 → 1.0 → 0.4 循环
        self._opacity = 1.0
        self._pulse = QPropertyAnimation(self, b"windowOpacity")
        self._pulse.setDuration(600)
        self._pulse.setStartValue(0.4)
        self._pulse.setEndValue(1.0)
        self._pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._pulse.setLoopCount(-1)  # 无限循环

    def show_at(self, x: int, y: int):
        """在指定坐标（鼠标位置）右下方显示加载指示。"""
        self.move(x + 12, y + 14)
        self.setWindowOpacity(1.0)
        self.show()
        self._pulse.start()

    def hide_dot(self):
        """隐藏加载指示。"""
        self._pulse.stop()
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._COLOR))
        offset = (self._WINDOW - self._SIZE) // 2
        painter.drawEllipse(offset, offset, self._SIZE, self._SIZE)
        painter.end()


# ══════════════════════════════════════════════════════════
#  独立运行测试
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    popup = PopupWidget()

    # 模拟测试数据
    test_data = {
        "word": "perceive",
        "phonetic": "/pəˈsiːv/",
        "translation": "vt. 察觉，感觉；理解；认知\nvt. 意识到；注意到",
        "definition": "v. to become aware of through the senses\nv. become conscious of",
        "collins_stars": 3,
        "collins_display": "★★★☆☆",
        "oxford": False,
        "bnc": 2776,
        "frq": 2165,
        "tags": ["cet4", "cet6", "ky", "toefl", "ielts"],
        "tag_display": "四级 六级 考研 托福 雅思",
        "exchange": {"d": "perceived", "p": "perceived", "3": "perceives", "i": "perceiving"},
        "is_lemma_result": False,
        "original_word": None,
    }

    # 在屏幕中央偏左显示
    screen = app.primaryScreen().geometry()
    popup.show_word(test_data, screen.width() // 3, screen.height() // 3)

    # 2 秒后显示一个 lemma 还原的示例
    from PyQt6.QtCore import QTimer

    def show_lemma_example():
        data2 = dict(test_data)
        data2["is_lemma_result"] = True
        data2["original_word"] = "perceived"
        popup.show_word(data2, screen.width() // 2, screen.height() // 2)

    QTimer.singleShot(3000, show_lemma_example)

    sys.exit(app.exec())
