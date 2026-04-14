"""
main.py — QuickDict 程序入口。

串联各模块：快捷键监听 → 屏幕取词 → 词典查询 → 弹窗显示。
"""
import sys
import ctypes
import ctypes.wintypes

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from quickdict.config import ensure_db
from quickdict.config import logger
from quickdict.dict_engine import DictEngine
from quickdict.hotkey import HotkeyListener
from quickdict.word_capture import WordCapture, CaptureMode
from quickdict.popup_widget import PopupWidget
from quickdict.app import TrayManager


# ── pynput 线程 → Qt 主线程桥接 ───────────────────────────

class _HotkeyBridge(QObject):
    """将 pynput 线程的回调安全地派发到 Qt 主线程。"""
    activated = pyqtSignal()
    deactivated = pyqtSignal()


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
        self._tray = TrayManager()
        self._tray.sig_toggle_capture.connect(self._on_tray_toggle)
        self._tray.sig_capture_mode_changed.connect(self._on_capture_mode_changed)
        self._tray.sig_quit.connect(self._quit)
        self._tray.show()

        # 启动键盘监听
        self._hotkey.start()
        logger.info("已启动 — 连按两次 Ctrl 激活取词，Esc 退出取词模式")

    # ── 取词模式控制 ──────────────────────────────────────

    def _on_activate(self):
        self._last_word = None
        self._poll_timer.start()
        self._tray.set_capture_enabled(True)
        self._tray.show_message("QuickDict", "取词模式已开启")

    def _on_deactivate(self):
        self._poll_timer.stop()
        self._popup.hide_popup()
        self._last_word = None
        self._tray.set_capture_enabled(False)

    def _on_tray_toggle(self):
        """托盘菜单点击「开启/关闭取词」→ 切换 HotkeyListener 状态。"""
        if self._hotkey.is_active:
            self._hotkey.stop()
            self._on_deactivate()
            self._tray.show_message("QuickDict", "取词已关闭，快捷键已停用")
        else:
            self._hotkey.start()
            self._tray.set_capture_enabled(False)
            self._tray.show_message("QuickDict", "快捷键已开启，连按 Ctrl×2 取词")

    _MODE_MAP = {
        "auto": CaptureMode.AUTO,
        "uia": CaptureMode.UIA_ONLY,
        "ocr": CaptureMode.OCR_ONLY,
    }
    _MODE_LABELS = {
        "auto": "自动（UIA→OCR）",
        "uia": "仅 UIA",
        "ocr": "仅 OCR",
    }

    def _on_capture_mode_changed(self, mode_key: str):
        """托盘菜单切换取词模式。"""
        mode = self._MODE_MAP.get(mode_key, CaptureMode.AUTO)
        self._capture.set_mode(mode)
        label = self._MODE_LABELS.get(mode_key, mode_key)
        self._tray.show_message("QuickDict", f"取词模式: {label}")

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
    # 设置 Per-Monitor DPI 感知（必须在 QApplication 之前调用）
    # 确保多显示器不同 DPI 下坐标正确，UI Automation 取词不受影响
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()  # 回退：System DPI Aware

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关闭弹窗不退出程序

    controller = QuickDictApp()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
