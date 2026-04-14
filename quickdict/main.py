"""
main.py — QuickDict 程序入口。

串联各模块：快捷键监听 → 屏幕取词 → 词典查询 → 弹窗显示。
"""
import os
import sys
import ctypes
import ctypes.wintypes

from PyQt6.QtCore import QObject, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from quickdict.config import ensure_db, load_settings, save_settings
from quickdict.config import logger
from quickdict.hotkey import HotkeyListener
from quickdict.word_capture import WordCapture, CaptureMode
from quickdict.popup_widget import PopupWidget, LoadingDot
from quickdict.app import TrayManager
from quickdict._lookup_worker import LookupWorker


# ── pynput 线程 → Qt 主线程桥接 ───────────────────────────

class _HotkeyBridge(QObject):
    """将 pynput 线程的回调安全地派发到 Qt 主线程。"""
    activated = pyqtSignal()
    deactivated = pyqtSignal()


# ── 主控制器 ──────────────────────────────────────────────

class QuickDictApp(QObject):
    """主程序控制器：管理各模块的生命周期和信号流。"""

    _sig_lookup = pyqtSignal(str, object)  # → LookupWorker.lookup

    _POLL_INTERVAL_MS = 50       # 光标位置检测间隔（ms）
    _SETTLE_MS = 80              # 鼠标静止后延迟取词（ms），人几乎无感知
    _JITTER_PX = 6               # 微抖动阈值（px），低于此视为静止
    _WORD_ZONE_BASE_PX = 15      # 同词区域基础半径（px）
    _WORD_ZONE_PER_CHAR_PX = 4   # 每字符额外的同词半径（px）
    _ABORT_MOVE_PX = 30          # 取词期间移动超此距离 → 中断取词

    def __init__(self):
        super().__init__()

        db_path = ensure_db()

        # 屏幕取词
        self._capture = WordCapture()
        self._settings = load_settings()

        # 恢复上次的取词模式
        saved_mode_key = self._settings.get("capture_mode", "auto")
        saved_mode = self._MODE_MAP.get(saved_mode_key, CaptureMode.AUTO)
        self._capture.set_mode(saved_mode)

        # 翻译弹窗
        self._popup = PopupWidget()
        self._loading = LoadingDot()

        # 后台查询线程（sqlite3 连接必须在使用线程中创建）
        self._worker = LookupWorker(db_path)
        self._worker_thread = QThread(self)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.init_engine)
        self._sig_lookup.connect(self._worker.lookup)
        self._worker.sig_result.connect(self._on_lookup_result)
        self._worker_thread.start()

        # 取词轮询定时器（高频检测鼠标位置，不直接取词）
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._on_poll)

        # 静止等待定时器（鼠标停住后延迟取词，消除时间抖动）
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(self._SETTLE_MS)
        self._settle_timer.timeout.connect(self._on_settle)

        # 轮询状态
        self._settle_pos: tuple[int, int] = (0, 0)
        self._anchor_pos: tuple[int, int] | None = None
        self._last_word: str | None = None
        self._word_zone_radius: int = self._WORD_ZONE_BASE_PX

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
        self._tray.set_capture_mode_checked(saved_mode_key)
        self._tray.show()

        # 启动键盘监听
        self._hotkey.start()
        logger.info("已启动 — 连按两次 Ctrl 激活取词，Esc 退出取词模式")

    # ── 取词模式控制 ──────────────────────────────────────

    def _on_activate(self):
        self._last_word = None
        self._anchor_pos = None
        self._settle_pos = self._get_cursor_pos()
        self._word_zone_radius = self._WORD_ZONE_BASE_PX
        self._poll_timer.start()
        self._tray.set_capture_enabled(True)
        self._tray.show_message("QECDict", "取词模式已开启", 500)

    def _on_deactivate(self):
        self._poll_timer.stop()
        self._settle_timer.stop()
        self._loading.hide_dot()
        self._popup.hide_popup()
        self._last_word = None
        self._anchor_pos = None
        self._tray.set_capture_enabled(False)

    def _on_tray_toggle(self):
        """托盘菜单点击「开启/关闭取词」→ 切换 HotkeyListener 状态。"""
        if self._hotkey.is_active:
            self._hotkey.stop()
            self._on_deactivate()
            self._tray.show_message("QECDict", "取词已关闭", 500)
        else:
            self._hotkey.start()
            self._tray.set_capture_enabled(False)
            self._tray.show_message("QECDict", "快捷键已开启，连按 Ctrl×2 取词", 500)

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
        """托盘菜单切换取词模式，保存到设置文件。"""
        mode = self._MODE_MAP.get(mode_key, CaptureMode.AUTO)
        self._capture.set_mode(mode)
        self._settings["capture_mode"] = mode_key
        save_settings(self._settings)
        label = self._MODE_LABELS.get(mode_key, mode_key)
        self._tray.show_message("QECDict", f"取词模式: {label}", 500)

    # ── 取词轮询 & 防抖 ──────────────────────────────────

    def _on_poll(self):
        """高频检测鼠标位置，鼠标在某处静止足够久才触发取词。"""
        x, y = self._get_cursor_pos()

        # 仍在当前词的空间区域内 → 无需重新取词
        if self._anchor_pos and self._last_word:
            ax, ay = self._anchor_pos
            adist = ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5
            if adist < self._word_zone_radius:
                return

        # 距 settle 起点的漂移量（用累计偏移代替逐帧偏移，避免慢速滑动时误触发）
        sx, sy = self._settle_pos
        drift = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5

        if drift < self._JITTER_PX:
            # 仍在 settle 起点附近 → 放行 settle 定时器继续倒计时
            return

        # 鼠标已漂移出 settle 起点 → 难开旧词区域，重新等待静止
        if self._last_word:
            self._popup.hide_popup()
            self._last_word = None
            self._anchor_pos = None
        self._loading.hide_dot()
        self._settle_pos = (x, y)
        self._settle_timer.start()

    def _on_settle(self):
        """鼠标静止足够久 → 显示加载指示，执行取词并查询。"""
        x, y = self._get_cursor_pos()

        # settle 期间鼠标大幅移动 → 放弃本次取词
        sx, sy = self._settle_pos
        if ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5 > self._ABORT_MOVE_PX:
            return

        # 显示加载指示
        self._loading.show_at(x, y)

        word = self._capture.capture(x, y)

        # 取词后再次检查：取词期间鼠标大幅移动 → 丢弃结果
        cx, cy = self._get_cursor_pos()
        if ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5 > self._ABORT_MOVE_PX:
            self._loading.hide_dot()
            return

        if not word:
            self._loading.hide_dot()
            if self._last_word:
                self._popup.hide_popup()
                self._last_word = None
                self._anchor_pos = None
            return

        # 同词 → 仅更新锚点位置
        if word == self._last_word:
            self._anchor_pos = (x, y)
            return

        # 新词 → 更新状态、计算词区域、发起查询
        self._anchor_pos = (x, y)
        self._last_word = word
        self._word_zone_radius = (self._WORD_ZONE_BASE_PX
                                  + len(word) * self._WORD_ZONE_PER_CHAR_PX)
        parts = self._capture.split_word(word)
        self._sig_lookup.emit(word, parts)

    def _on_lookup_result(self, word: str, data):
        """后台查询完成 → 隐藏加载指示，在主线程显示弹窗。"""
        self._loading.hide_dot()
        # 查询期间单词已变 → 丢弃过期结果
        if word != self._last_word:
            return
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
        self._poll_timer.stop()
        self._settle_timer.stop()
        self._hotkey.stop()
        self._tray.hide()
        self._worker_thread.quit()
        self._worker_thread.wait(1000)
        QApplication.quit()
        os._exit(0)


# ── 入口 ──────────────────────────────────────────────────

def main():
    # 设置 Per-Monitor DPI 感知（必须在 QApplication 之前调用）
    # 确保多显示器不同 DPI 下坐标正确，UI Automation 取词不受影响
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()  # 回退：System DPI Aware

    app = QApplication(sys.argv)
    app.setApplicationName("QECDict")
    app.setQuitOnLastWindowClosed(False)  # 关闭弹窗不退出程序

    controller = QuickDictApp()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
