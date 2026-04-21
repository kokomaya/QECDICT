"""LinguaLens — QuickDict + MagicMirror 合体，统一托盘入口。"""

import ctypes
import faulthandler
import logging
import os
import signal
import sys
import traceback
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def _get_log_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "lingualens.log")
    return "lingualens.log"


def main() -> None:
    debug = "--debug" in sys.argv

    # ── 日志配置 ──
    log_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    if debug:
        log_file = _get_log_path()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n[STARTUP] {datetime.now()} frozen={getattr(sys, 'frozen', False)}\n")

        _fault_fh = open(log_file, "a", encoding="utf-8")
        faulthandler.enable(file=_fault_fh)

        def _excepthook(exc_type, exc_value, exc_tb):
            with open(log_file, "a", encoding="utf-8") as fh:
                fh.write(f"\n[UNHANDLED] {datetime.now()}\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=fh)
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        sys.excepthook = _excepthook

        handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
        if sys.stderr is not None:
            handlers.append(logging.StreamHandler())
        logging.basicConfig(level=logging.DEBUG, format=log_fmt, handlers=handlers, force=True)
    else:
        logging.basicConfig(level=logging.WARNING, format=log_fmt)

    logger = logging.getLogger("lingualens")

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()

    app = QApplication(sys.argv)
    app.setApplicationName("LinguaLens")
    app.setQuitOnLastWindowClosed(False)

    signal.signal(signal.SIGINT, lambda *_: QApplication.quit())
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(200)

    # ── QuickDict ──
    from quickdict.config import ensure_db, load_settings
    ensure_db()
    load_settings()
    from quickdict.main import QuickDictApp
    quickdict = QuickDictApp()
    quickdict._tray.hide()

    # ── MagicMirror ──
    from magic_mirror.config import load_env, load_llm_config
    from magic_mirror.main import create_pipeline, StreamTranslateApp
    load_env()
    try:
        pipeline = create_pipeline()
        mirror = StreamTranslateApp(pipeline)
        mirror._tray.hide()
        has_mirror = True
    except Exception as e:
        logger.warning("MagicMirror 初始化失败 (翻译功能不可用): %s", e)
        mirror = None
        has_mirror = False

    # ── 统一托盘 ──
    tray = _build_tray(app, quickdict, mirror, has_mirror)

    def cleanup():
        if has_mirror:
            mirror.cleanup()
        quickdict._quit()

    app.aboutToQuit.connect(cleanup)

    logger.info("LinguaLens 已启动 (QuickDict + MagicMirror)")
    sys.exit(app.exec())


def _build_tray(app, quickdict, mirror, has_mirror):
    icon = _create_icon()
    tray = QSystemTrayIcon(icon)
    tray.setToolTip("LinguaLens — 取词 & 翻译")

    menu = QMenu()

    # ── QuickDict 区 ──
    header_qd = QAction("── QuickDict 取词 ──", menu)
    header_qd.setEnabled(False)
    menu.addAction(header_qd)

    act_toggle = menu.addAction("开启取词")
    def toggle_capture():
        quickdict._tray.sig_toggle_capture.emit()
    act_toggle.triggered.connect(toggle_capture)

    def on_capture_state_changed(enabled):
        act_toggle.setText("关闭取词" if enabled else "开启取词")
    quickdict._tray.sig_toggle_capture.connect(
        lambda: QTimer.singleShot(50, lambda: on_capture_state_changed(quickdict._tray._capture_enabled))
    )

    menu.addSeparator()

    # ── MagicMirror 区 ──
    if has_mirror:
        header_mm = QAction("── MagicMirror 翻译 ──", menu)
        header_mm.setEnabled(False)
        menu.addAction(header_mm)

        act_translate = QAction("翻译区域 (Ctrl+Alt+T)", menu)
        act_translate.triggered.connect(mirror._on_hotkey)
        menu.addAction(act_translate)

        act_ocr = QAction("提取文本 (Ctrl+Alt+C)", menu)
        act_ocr.triggered.connect(mirror._on_ocr_copy_hotkey)
        menu.addAction(act_ocr)

        act_close_all = QAction("关闭全部覆盖层", menu)
        act_close_all.triggered.connect(mirror._close_all_overlays)
        menu.addAction(act_close_all)

        act_chat = QAction("AI 聊天 (Ctrl+Alt+D)", menu)
        act_chat.triggered.connect(mirror._on_chat_hotkey)
        menu.addAction(act_chat)

        menu.addSeparator()

    # ── 公共 ──
    act_quit = QAction("退出", menu)
    act_quit.triggered.connect(QApplication.quit)
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.show()

    # prevent GC
    app._lingualens_tray = tray
    app._lingualens_menu = menu

    return tray


def _create_icon():
    size = 32
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setBrush(QColor(0, 150, 136))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)

    font = QFont("Segoe UI", 16)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "L")

    p.end()
    return QIcon(pm)


if __name__ == "__main__":
    main()
