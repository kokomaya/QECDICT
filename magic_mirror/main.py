"""主程序集成 — 组装所有组件，串联 UI 交互与翻译管线。

Composition Root：这是整个项目中唯一 import 具体实现类的地方。
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import List, Tuple

from PyQt6.QtCore import QObject, QRect, QRunnable, QThreadPool, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from magic_mirror.config import load_env, load_llm_config
from magic_mirror.config.settings import HOTKEY_TRIGGER
from magic_mirror.interfaces.types import RenderBlock
from magic_mirror.pipeline import TranslatePipeline

# ── 具体实现类（仅在此处 import）──
from magic_mirror.capture.pil_capture import PilScreenCapture
from magic_mirror.capture.region_selector import RegionSelector
from magic_mirror.layout.layout_engine import DefaultLayoutEngine
from magic_mirror.ocr.rapid_ocr_engine import RapidOcrEngine
from magic_mirror.translation.provider_factory import create_translator_from_config
from magic_mirror.ui.loading_indicator import LoadingIndicator
from magic_mirror.ui.mirror_overlay import MirrorOverlay

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Composition Root
# ------------------------------------------------------------------

def create_pipeline() -> TranslatePipeline:
    """创建翻译管线，注入所有具体实现。"""
    return TranslatePipeline(
        capture=PilScreenCapture(),
        ocr=RapidOcrEngine(),
        translator=create_translator_from_config(),
        layout=DefaultLayoutEngine(),
    )


# ------------------------------------------------------------------
# 管线工作线程
# ------------------------------------------------------------------

class _PipelineWorker(QRunnable):
    """在线程池中执行翻译管线的 Runnable。"""

    class Signals(QObject):
        finished = pyqtSignal(list, tuple)   # (render_blocks, screen_bbox)
        error = pyqtSignal(str)              # error message

    def __init__(
        self,
        pipeline: TranslatePipeline,
        bbox: Tuple[int, int, int, int],
    ) -> None:
        super().__init__()
        self.signals = self.Signals()
        self._pipeline = pipeline
        self._bbox = bbox

    def run(self) -> None:
        try:
            render_blocks, screen_bbox = self._pipeline.execute(self._bbox)
            self.signals.finished.emit(render_blocks, screen_bbox)
        except Exception as exc:
            logger.exception("管线执行失败")
            self.signals.error.emit(str(exc))


# ------------------------------------------------------------------
# 热键解析
# ------------------------------------------------------------------

def _parse_hotkey(hotkey_str: str):
    """将 'ctrl+alt+t' 格式字符串解析为 pynput 按键集合。"""
    from pynput.keyboard import Key, KeyCode

    _KEY_MAP = {
        "ctrl": Key.ctrl_l,
        "alt": Key.alt_l,
        "shift": Key.shift_l,
    }

    keys = set()
    for part in hotkey_str.lower().split("+"):
        part = part.strip()
        if part in _KEY_MAP:
            keys.add(_KEY_MAP[part])
        elif len(part) == 1:
            keys.add(KeyCode.from_char(part))
        else:
            logger.warning("未知热键部分: %s", part)
    return keys


# ------------------------------------------------------------------
# 应用控制器
# ------------------------------------------------------------------

class StreamTranslateApp(QObject):
    """应用控制器 — 热键监听 + UI 信号流 + 管线调度。"""

    # 用信号将热键线程的触发安全传回主线程
    _sig_hotkey_triggered = pyqtSignal()

    def __init__(self, pipeline: TranslatePipeline, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._pipeline = pipeline

        # UI 组件
        self._selector = RegionSelector()
        self._overlay = MirrorOverlay()
        self._loading = LoadingIndicator()

        # 信号连接
        self._selector.sig_region_selected.connect(self._on_region_selected)
        self._sig_hotkey_triggered.connect(self._on_hotkey)

        # 热键监听
        self._hotkey_keys = _parse_hotkey(HOTKEY_TRIGGER)
        self._pressed_keys: set = set()
        self._start_hotkey_listener()

        # 系统托盘
        self._setup_tray()

    # ── 热键 ──

    def _start_hotkey_listener(self) -> None:
        from pynput.keyboard import Listener

        def on_press(key):
            self._pressed_keys.add(key)
            if self._hotkey_keys.issubset(self._pressed_keys):
                self._sig_hotkey_triggered.emit()

        def on_release(key):
            self._pressed_keys.discard(key)

        self._listener = Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    @pyqtSlot()
    def _on_hotkey(self) -> None:
        """热键触发 → 关闭旧覆盖 → 启动框选。"""
        self._overlay.close_overlay()
        self._selector.start()

    # ── 框选完成 ──

    @pyqtSlot(QRect)
    def _on_region_selected(self, rect: QRect) -> None:
        bbox = (rect.x(), rect.y(), rect.width(), rect.height())
        logger.info("区域选定: %s", bbox)

        self._loading.show_at(bbox)

        worker = _PipelineWorker(self._pipeline, bbox)
        worker.signals.finished.connect(self._on_pipeline_done)
        worker.signals.error.connect(self._on_pipeline_error)
        # 防止 worker 被 GC
        self._current_worker = worker
        QThreadPool.globalInstance().start(worker)

    @pyqtSlot(list, tuple)
    def _on_pipeline_done(
        self,
        render_blocks: List[RenderBlock],
        screen_bbox: tuple,
    ) -> None:
        self._loading.dismiss()
        if render_blocks:
            self._overlay.render(render_blocks, screen_bbox)
        else:
            logger.info("无翻译结果")

    @pyqtSlot(str)
    def _on_pipeline_error(self, msg: str) -> None:
        self._loading.dismiss()
        logger.error("翻译失败: %s", msg)

    # ── 系统托盘 ──

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        self._tray.setToolTip("Magic Mirror — 屏幕翻译")

        menu = QMenu()
        act_translate = QAction("翻译区域 (Ctrl+Alt+T)", menu)
        act_translate.triggered.connect(self._on_hotkey)
        menu.addAction(act_translate)

        menu.addSeparator()

        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.show()


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

def main() -> None:
    # Windows DPI 感知
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 托盘应用不随窗口关闭退出

    # 加载配置
    load_env()

    try:
        pipeline = create_pipeline()
    except FileNotFoundError as e:
        logger.error("配置缺失:\n%s", e)
        sys.exit(1)

    controller = StreamTranslateApp(pipeline)  # noqa: F841 — prevent GC

    logger.info("Magic Mirror 已启动，按 %s 开始翻译", HOTKEY_TRIGGER)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()