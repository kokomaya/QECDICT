"""
app.py — 系统托盘 & 后台常驻管理。

职责单一：管理 QSystemTrayIcon、右键菜单、托盘交互。
通过 Qt 信号向外部暴露用户操作，不含取词/查词逻辑。
"""

import os

from PyQt6.QtCore import QObject, QPoint, QPropertyAnimation, QTimer, pyqtSignal, QEasingCurve
from PyQt6.QtWidgets import QApplication, QLabel, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction, QActionGroup, QPainterPath, QPen, QBrush
from PyQt6.QtCore import Qt, QRectF

from quickdict.config import ASSETS_DIR

_ICON_PATH = os.path.join(ASSETS_DIR, "icon.png")


class TrayManager(QObject):
    """
    系统托盘管理器。

    信号:
        sig_toggle_capture: 用户点击「开启/关闭取词」
        sig_open_settings:  用户点击「设置」或双击托盘
        sig_open_history:   用户点击「查词历史」
        sig_quit:           用户点击「退出」
    """

    sig_toggle_capture = pyqtSignal()
    sig_capture_mode_changed = pyqtSignal(str)  # "auto" / "uia" / "ocr"
    sig_trigger_mode_changed = pyqtSignal(str)  # "hover" / "ctrl"
    sig_open_settings = pyqtSignal()
    sig_open_history = pyqtSignal()
    sig_quit = pyqtSignal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._capture_enabled = False
        self._tray = QSystemTrayIcon(self._load_icon(), parent)
        self._tray.setToolTip("QECDict — 连按 Ctrl×2 取词")

        # 右键菜单
        self._menu = QMenu()
        self._action_toggle = self._menu.addAction("开启取词")
        self._action_toggle.triggered.connect(self._on_toggle_clicked)

        # 取词模式子菜单
        self._mode_menu = self._menu.addMenu("取词模式")
        self._mode_group = QActionGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_actions: dict[str, QAction] = {}
        for key, label in [("auto", "自动（UIA→OCR）"), ("uia", "仅 UIA"), ("ocr", "仅 OCR")]:
            action = self._mode_menu.addAction(label)
            action.setCheckable(True)
            action.setActionGroup(self._mode_group)
            action.setData(key)
            action.triggered.connect(lambda checked, k=key: self.sig_capture_mode_changed.emit(k))
            self._mode_actions[key] = action
        self._mode_actions["auto"].setChecked(True)

        # 触发方式子菜单
        self._trigger_menu = self._menu.addMenu("触发方式")
        self._trigger_group = QActionGroup(self)
        self._trigger_group.setExclusive(True)
        self._trigger_actions: dict[str, QAction] = {}
        for key, label in [("hover", "悬停取词"), ("ctrl", "Ctrl 键取词")]:
            action = self._trigger_menu.addAction(label)
            action.setCheckable(True)
            action.setActionGroup(self._trigger_group)
            action.setData(key)
            action.triggered.connect(lambda checked, k=key: self.sig_trigger_mode_changed.emit(k))
            self._trigger_actions[key] = action
        self._trigger_actions["ctrl"].setChecked(True)

        self._menu.addSeparator()
        self._action_history = self._menu.addAction("查词历史（暂不支持）")
        self._action_history.setEnabled(False)
        self._action_settings = self._menu.addAction("设置（暂不支持）")
        self._action_settings.setEnabled(False)
        self._menu.addSeparator()
        action_quit = self._menu.addAction("退出")
        action_quit.triggered.connect(self.sig_quit.emit)

        self._tray.setContextMenu(self._menu)

        # 双击打开设置
        self._tray.activated.connect(self._on_tray_activated)

    # ── 公开接口 ──────────────────────────────────────────

    def show(self):
        """显示托盘图标。"""
        self._tray.show()

    def hide(self):
        """隐藏托盘图标。"""
        self._tray.hide()

    def set_capture_enabled(self, enabled: bool):
        """外部通知取词模式状态变更，更新菜单文本。"""
        self._capture_enabled = enabled
        self._action_toggle.setText("关闭取词 ✓" if enabled else "开启取词")

    def set_capture_mode_checked(self, mode_key: str):
        """设置取词模式菜单的选中状态。"""
        action = self._mode_actions.get(mode_key)
        if action:
            action.setChecked(True)

    def set_trigger_mode_checked(self, mode_key: str):
        """设置触发方式菜单的选中状态。"""
        action = self._trigger_actions.get(mode_key)
        if action:
            action.setChecked(True)

    def show_message(self, title: str, message: str, duration_ms: int = 800):
        """显示轻量 toast 提示（半透明，自动淡出）。"""
        if not hasattr(self, "_toast") or self._toast is None:
            self._toast = _ToastLabel()
        self._toast.show_toast(message, duration_ms)

    # ── 内部逻辑 ──────────────────────────────────────────

    def _on_toggle_clicked(self):
        """菜单「开启/关闭取词」被点击。"""
        self.sig_toggle_capture.emit()

    def _on_tray_activated(self, reason):
        """托盘图标被交互（双击 → 打开设置）。"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.sig_open_settings.emit()

    @staticmethod
    def _load_icon() -> QIcon:
        """加载托盘图标：优先 assets/icon.png，回退到运行时绘制。"""
        if os.path.isfile(_ICON_PATH):
            return QIcon(_ICON_PATH)
        return TrayManager._make_fallback_icon()

    @staticmethod
    def _make_fallback_icon() -> QIcon:
        """运行时生成备用图标。"""
        size = 64
        pm = QPixmap(size, size)
        pm.fill(QColor(67, 97, 238))
        painter = QPainter(pm)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "D")
        painter.end()
        return QIcon(pm)


# ── 轻量 Toast 提示 ──────────────────────────────────────

class _ToastLabel(QLabel):
    """半透明自动淡出的轻量提示，替代系统托盘气泡通知。"""

    _BG_COLOR = QColor(30, 30, 46, 230)
    _TEXT_COLOR = QColor(255, 255, 255)
    _BORDER_RADIUS = 6
    _PADDING_H = 14
    _PADDING_V = 6

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFont(QFont("Microsoft YaHei", 10))
        self._fade_anim: QPropertyAnimation | None = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def paintEvent(self, event):
        """手动绘制圆角背景 + 文字，避免 WA_TranslucentBackground 下 QSS 不生效。"""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 圆角背景
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._BORDER_RADIUS, self._BORDER_RADIUS)
        p.fillPath(path, QBrush(self._BG_COLOR))
        # 文字
        p.setPen(self._TEXT_COLOR)
        p.setFont(self.font())
        text_rect = self.rect().adjusted(self._PADDING_H, self._PADDING_V,
                                         -self._PADDING_H, -self._PADDING_V)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text())
        p.end()
        self._fade_anim: QPropertyAnimation | None = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

    def show_toast(self, text: str, duration_ms: int = 800):
        """在屏幕右下角显示提示，duration_ms 后淡出。"""
        self._hide_timer.stop()
        if self._fade_anim:
            self._fade_anim.stop()

        self.setText(text)
        fm = self.fontMetrics()
        w = fm.horizontalAdvance(text) + self._PADDING_H * 2
        h = fm.height() + self._PADDING_V * 2
        self.setFixedSize(w, h)
        self.setWindowOpacity(0.95)

        # 定位到屏幕右下角（托盘附近）
        screen = QApplication.primaryScreen()
        sr = screen.availableGeometry()
        x = sr.right() - self.width() - 16
        y = sr.bottom() - self.height() - 16
        self.move(x, y)

        self.show()
        self._hide_timer.start(duration_ms)

    def _fade_out(self):
        """淡出动画后隐藏。"""
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()
