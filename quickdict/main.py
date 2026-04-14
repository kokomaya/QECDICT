"""
main.py — QuickDict 程序入口。

串联各模块：快捷键监听 → 屏幕取词 → 词典查询 → 弹窗显示。
"""
import sys
import os
import ctypes
import ctypes.wintypes

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, Qt
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont

from quickdict.config import ensure_db
from quickdict.dict_engine import DictEngine
from quickdict.hotkey import HotkeyListener
from quickdict.word_capture import WordCapture
from quickdict.popup_widget import PopupWidget


# ── pynput 线程 → Qt 主线程桥接 ───────────────────────────

class _HotkeyBridge(QObject):
    """将 pynput 线程的回调安全地派发到 Qt 主线程。"""
    activated = pyqtSignal()
    deactivated = pyqtSignal()


# ── 托盘图标生成 ──────────────────────────────────────────

def _make_tray_icon() -> QIcon:
    """生成一个简易的 'D' 字母图标作为托盘图标。"""
    size = 64
    pm = QPixmap(size, size)
    pm.fill(QColor(67, 97, 238))  # #4361EE
    painter = QPainter(pm)
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
    painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "D")
    painter.end()
    return QIcon(pm)


# ── 主控制器 ──────────────────────────────────────────────

class QuickDictApp(QObject):
    """主程序控制器：管理各模块的生命周期和信号流。"""

    _POLL_INTERVAL_MS = 200  # 取词轮询间隔

    def __init__(self):
        super().__init__()

        # 词典引擎
        db_path = ensure_db()
        self._engine = DictEngine(db_path)

        # 屏幕取词
        self._capture = WordCapture()

        # 翻译弹窗
        self._popup = PopupWidget()

        # 取词轮询定时器
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._on_poll)
        self._last_word: str | None = None

        # 快捷键监听（pynput 线程 → Qt 信号桥接）
        self._bridge = _HotkeyBridge()
        self._bridge.activated.connect(self._on_activate)
        self._bridge.deactivated.connect(self._on_deactivate)
        self._hotkey = HotkeyListener(
            on_activate=self._bridge.activated.emit,
            on_deactivate=self._bridge.deactivated.emit,
        )

        # 系统托盘
        self._tray = self._init_tray()

        # 启动
        self._hotkey.start()
        print("[QuickDict] 已启动 — 连按两次 Ctrl 激活取词，Esc 退出取词模式")

    # ── 系统托盘 ──────────────────────────────────────────

    def _init_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(_make_tray_icon())
        tray.setToolTip("QuickDict — 连按 Ctrl×2 取词")

        menu = QMenu()
        self._action_toggle = menu.addAction("开启取词")
        self._action_toggle.setEnabled(False)
        menu.addSeparator()
        action_quit = menu.addAction("退出")
        action_quit.triggered.connect(self._quit)
        tray.setContextMenu(menu)
        tray.show()
        return tray

    # ── 取词模式控制 ──────────────────────────────────────

    def _on_activate(self):
        self._last_word = None
        self._poll_timer.start()
        self._action_toggle.setText("取词模式已开启 ✓")
        self._tray.showMessage("QuickDict", "取词模式已开启", QSystemTrayIcon.MessageIcon.Information, 1000)

    def _on_deactivate(self):
        self._poll_timer.stop()
        self._popup.hide_popup()
        self._last_word = None
        self._action_toggle.setText("取词模式已关闭")

    # ── 取词轮询 ──────────────────────────────────────────

    def _on_poll(self):
        """每 200ms 检测鼠标下的单词并查询。"""
        word = self._capture.capture()
        if not word or word == self._last_word:
            return

        self._last_word = word
        data = self._engine.lookup(word)
        if not data:
            # 如果是复合词，尝试拆分后查第一个
            parts = self._capture.capture_split()
            for part in parts:
                data = self._engine.lookup(part)
                if data:
                    break

        if data:
            x, y = self._get_cursor_pos()
            self._popup.show_word(data, x, y)

    @staticmethod
    def _get_cursor_pos() -> tuple[int, int]:
        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    # ── 退出 ──────────────────────────────────────────────

    def _quit(self):
        self._hotkey.stop()
        self._poll_timer.stop()
        self._engine.close()
        self._tray.hide()
        QApplication.quit()


# ── 入口 ──────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭弹窗不退出程序

    controller = QuickDictApp()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
