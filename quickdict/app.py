"""
app.py — 系统托盘 & 后台常驻管理。

职责单一：管理 QSystemTrayIcon、右键菜单、托盘交互。
通过 Qt 信号向外部暴露用户操作，不含取词/查词逻辑。
"""

import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction
from PyQt6.QtCore import Qt

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
    sig_open_settings = pyqtSignal()
    sig_open_history = pyqtSignal()
    sig_quit = pyqtSignal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._capture_enabled = False
        self._tray = QSystemTrayIcon(self._load_icon(), parent)
        self._tray.setToolTip("QuickDict — 连按 Ctrl×2 取词")

        # 右键菜单
        self._menu = QMenu()
        self._action_toggle = self._menu.addAction("开启取词")
        self._action_toggle.triggered.connect(self._on_toggle_clicked)
        self._menu.addSeparator()
        self._action_history = self._menu.addAction("查词历史")
        self._action_history.triggered.connect(self.sig_open_history.emit)
        self._action_settings = self._menu.addAction("设置")
        self._action_settings.triggered.connect(self.sig_open_settings.emit)
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

    def show_message(self, title: str, message: str, duration_ms: int = 1500):
        """在托盘弹出气泡通知。"""
        self._tray.showMessage(
            title, message,
            QSystemTrayIcon.MessageIcon.Information, duration_ms,
        )

    # ── 内部逻辑 ──────────────────────────────────────────

    def _on_toggle_clicked(self):
        """菜单「开启/关闭取词」被点击。"""
        self.sig_toggle_capture.emit()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
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
