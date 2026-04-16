"""主程序集成 — 组装所有组件，串联 UI 交互与翻译管线。

Composition Root：这是整个项目中唯一 import 具体实现类的地方。
"""

from __future__ import annotations

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
# 热键工具
# ------------------------------------------------------------------

def _normalize_key(key) -> str:
    """将 pynput key 对象统一为可比较的字符串标签。

    pynput 在不同事件中可能返回 Key.ctrl_l / Key.ctrl_r / KeyCode(vk=...) 等
    不同对象，直接用 set 比较会失败。这里统一映射到小写字符串。
    """
    from pynput.keyboard import Key, KeyCode

    # 特殊键：ctrl_l/ctrl_r → "ctrl"
    _SPECIAL_MAP = {
        Key.ctrl_l: "ctrl", Key.ctrl_r: "ctrl",
        Key.alt_l: "alt", Key.alt_r: "alt", Key.alt_gr: "alt",
        Key.shift_l: "shift", Key.shift_r: "shift",
    }
    if key in _SPECIAL_MAP:
        return _SPECIAL_MAP[key]

    # 普通字符键
    if isinstance(key, KeyCode):
        if key.char:
            return key.char.lower()
        if key.vk is not None:
            # vk 65-90 = A-Z
            if 65 <= key.vk <= 90:
                return chr(key.vk).lower()
    return str(key)


def _parse_hotkey(hotkey_str: str) -> set:
    """将 'ctrl+alt+t' 格式字符串解析为归一化标签集合。"""
    labels = set()
    for part in hotkey_str.lower().split("+"):
        labels.add(part.strip())
    return labels


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
        self._hotkey_labels = _parse_hotkey(HOTKEY_TRIGGER)
        self._pressed_labels: set = set()
        logger.debug("注册热键: %s → 标签集 %s", HOTKEY_TRIGGER, self._hotkey_labels)
        self._start_hotkey_listener()

        # 系统托盘
        self._setup_tray()

    # ── 热键 ──

    def _start_hotkey_listener(self) -> None:
        from pynput.keyboard import Listener

        def on_press(key):
            label = _normalize_key(key)
            self._pressed_labels.add(label)
            logger.debug("key press: %s → label=%s, active=%s", key, label, self._pressed_labels)
            if self._hotkey_labels.issubset(self._pressed_labels):
                logger.info("热键匹配! 触发框选")
                self._pressed_labels.clear()  # 防止重复触发
                self._sig_hotkey_triggered.emit()

        def on_release(key):
            label = _normalize_key(key)
            self._pressed_labels.discard(label)

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
    # 解析命令行参数
    debug = "--debug" in sys.argv

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
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