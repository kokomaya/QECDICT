"""主程序集成 — 组装所有组件，串联 UI 交互与翻译管线。

Composition Root：这是整个项目中唯一 import 具体实现类的地方。
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import List, Tuple

from PyQt6.QtCore import QObject, QRect, QRunnable, QThreadPool, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from magic_mirror.config import load_env, load_llm_config
from magic_mirror.config.settings import HOTKEY_OCR_COPY, HOTKEY_TRIGGER
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
from magic_mirror.ui.text_overlay import TextOverlay
from magic_mirror.ui.chat_dialog import ChatDialog

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


class _PipelineWorkerWithCapture(QRunnable):
    """已有截图结果时，跳过截图步骤执行后续管线。"""

    class Signals(QObject):
        finished = pyqtSignal(list, tuple)
        error = pyqtSignal(str)

    def __init__(self, pipeline: TranslatePipeline, capture_result) -> None:
        super().__init__()
        self.signals = self.Signals()
        self._pipeline = pipeline
        self._capture_result = capture_result

    def run(self) -> None:
        try:
            render_blocks, screen_bbox = self._pipeline.execute_from_capture(
                self._capture_result,
            )
            self.signals.finished.emit(render_blocks, screen_bbox)
        except Exception as exc:
            logger.exception("管线执行失败")
            self.signals.error.emit(str(exc))


class _OcrCopyWorker(QRunnable):
    """OCR 提取文本并计算渲染布局的工作线程。"""

    class Signals(QObject):
        finished = pyqtSignal(list)   # List[RenderBlock]
        error = pyqtSignal(str)

    def __init__(self, pipeline: TranslatePipeline, capture_result) -> None:
        super().__init__()
        self.signals = self.Signals()
        self._pipeline = pipeline
        self._capture_result = capture_result

    def run(self) -> None:
        try:
            from magic_mirror.interfaces.types import TranslatedBlock

            image = self._capture_result.image
            screen_bbox = self._capture_result.screen_bbox
            text_blocks = self._pipeline._ocr.recognize(image)
            if not text_blocks:
                self.signals.finished.emit([])
                return

            # 将原文包装为 TranslatedBlock（translated_text = 原文）
            pseudo_translated = [
                TranslatedBlock(source=tb, translated_text=tb.text)
                for tb in text_blocks
            ]
            render_blocks = self._pipeline._layout.compute_layout(
                pseudo_translated, image, screen_bbox,
            )
            self.signals.finished.emit(render_blocks)
        except Exception as exc:
            logger.exception("OCR 提取失败")
            self.signals.error.emit(str(exc))


class _StreamingPipelineWorker(QRunnable):
    """流式管线工作线程：逐条翻译并通过信号通知 UI。"""

    class Signals(QObject):
        ocr_done = pyqtSignal(list, tuple)           # (text_blocks, screen_bbox)
        block_ready = pyqtSignal(object, tuple)     # (RenderBlock, screen_bbox)
        finished = pyqtSignal(tuple)                 # screen_bbox
        error = pyqtSignal(str)

    def __init__(self, pipeline: TranslatePipeline, capture_result, screen_bbox) -> None:
        super().__init__()
        self.signals = self.Signals()
        self._pipeline = pipeline
        self._capture_result = capture_result
        self._screen_bbox = screen_bbox

    def run(self) -> None:
        try:
            def on_block(rb):
                self.signals.block_ready.emit(rb, self._screen_bbox)

            def on_ocr(text_blocks):
                self.signals.ocr_done.emit(text_blocks, self._screen_bbox)

            self._pipeline.execute_streaming_from_capture(
                self._capture_result,
                on_block_ready=on_block,
                on_ocr_done=on_ocr,
            )
            self.signals.finished.emit(self._screen_bbox)
        except Exception as exc:
            logger.exception("流式管线执行失败")
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
        Key.esc: "escape",
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
    _sig_ocr_copy_triggered = pyqtSignal()      # OCR 提取原文
    _sig_close_last_overlay = pyqtSignal()      # Esc 关闭最近一个覆盖层
    _sig_close_all_overlays = pyqtSignal()      # Ctrl+Shift+Esc 关闭全部

    # 框选完成后的操作模式
    _MODE_TRANSLATE = "translate"
    _MODE_OCR_COPY = "ocr_copy"

    def __init__(self, pipeline: TranslatePipeline, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._pipeline = pipeline
        self._pending_mode = self._MODE_TRANSLATE

        # UI 组件
        self._selector = RegionSelector()
        self._overlays: List[MirrorOverlay] = []   # 多覆盖层
        self._loading = LoadingIndicator()

        # 信号连接
        self._selector.sig_region_selected.connect(self._on_region_selected)
        self._sig_hotkey_triggered.connect(self._on_hotkey)
        self._sig_ocr_copy_triggered.connect(self._on_ocr_copy_hotkey)
        self._sig_close_last_overlay.connect(self._close_last_overlay)
        self._sig_close_all_overlays.connect(self._close_all_overlays)

        # 热键监听
        self._hotkey_labels = _parse_hotkey(HOTKEY_TRIGGER)
        self._ocr_copy_labels = _parse_hotkey(HOTKEY_OCR_COPY)
        self._pressed_labels: set = set()
        logger.debug("注册热键: %s → %s, %s → %s",
                     HOTKEY_TRIGGER, self._hotkey_labels,
                     HOTKEY_OCR_COPY, self._ocr_copy_labels)
        self._start_hotkey_listener()

        # 系统托盘
        self._setup_tray()

    # ── 热键 ──

    def _start_hotkey_listener(self) -> None:
        from pynput.keyboard import Key, Listener

        def on_press(key):
            label = _normalize_key(key)
            self._pressed_labels.add(label)
            logger.debug("key press: %s → label=%s, active=%s", key, label, self._pressed_labels)

            # Ctrl+Alt+T → 新建翻译
            if self._hotkey_labels.issubset(self._pressed_labels):
                logger.info("热键匹配! 触发翻译框选")
                self._pressed_labels.clear()
                self._sig_hotkey_triggered.emit()
            # Ctrl+Alt+C → OCR 提取原文
            elif self._ocr_copy_labels.issubset(self._pressed_labels):
                logger.info("热键匹配! 触发 OCR 提取")
                self._pressed_labels.clear()
                self._sig_ocr_copy_triggered.emit()
            # Ctrl+Shift+Esc → 关闭全部覆盖层
            elif {"ctrl", "shift", "escape"}.issubset(self._pressed_labels):
                logger.info("关闭全部覆盖层")
                self._pressed_labels.clear()
                self._sig_close_all_overlays.emit()
            # Esc → 关闭最近一个覆盖层
            elif key == Key.esc:
                self._sig_close_last_overlay.emit()

        def on_release(key):
            label = _normalize_key(key)
            self._pressed_labels.discard(label)

        self._listener = Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def cleanup(self) -> None:
        """退出时停止热键监听线程，关闭所有覆盖层。"""
        if hasattr(self, '_listener') and self._listener.is_alive():
            self._listener.stop()
            logger.debug("热键监听器已停止")
        for overlay in self._overlays:
            overlay.close_overlay()
        self._overlays.clear()

    @pyqtSlot()
    def _on_hotkey(self) -> None:
        """翻译热键触发 → 启动框选。"""
        self._pending_mode = self._MODE_TRANSLATE
        self._selector.start()

    @pyqtSlot()
    def _on_ocr_copy_hotkey(self) -> None:
        """OCR 提取热键触发 → 启动框选（提取模式）。"""
        self._pending_mode = self._MODE_OCR_COPY
        self._selector.start()

    @pyqtSlot()
    def _close_last_overlay(self) -> None:
        """Esc → 关闭最近一个覆盖层。"""
        if self._overlays:
            overlay = self._overlays.pop()
            overlay.close_overlay()
            overlay.deleteLater()
            logger.debug("关闭最近覆盖层，剩余 %d 个", len(self._overlays))

    @pyqtSlot()
    def _close_all_overlays(self) -> None:
        """关闭全部覆盖层。"""
        for overlay in self._overlays:
            overlay.close_overlay()
            overlay.deleteLater()
        count = len(self._overlays)
        self._overlays.clear()
        logger.info("已关闭全部 %d 个覆盖层", count)

    # ── 框选完成 ──

    @pyqtSlot(QRect)
    def _on_region_selected(self, rect: QRect) -> None:
        bbox = (rect.x(), rect.y(), rect.width(), rect.height())
        logger.info("区域选定: %s (模式=%s)", bbox, self._pending_mode)

        # 先截图再显示 loading，避免 loading 文字被 OCR 识别
        try:
            capture_result = self._pipeline._capture.capture(bbox)
        except Exception as exc:
            logger.error("截图失败: %s", exc)
            return

        if self._pending_mode == self._MODE_OCR_COPY:
            self._run_ocr_copy(capture_result, bbox)
        else:
            self._run_translate(capture_result, bbox)

    def _run_translate(self, capture_result, bbox: tuple) -> None:
        """翻译模式：OCR → 翻译 → 覆盖层渲染。"""
        self._loading.show_at(bbox)

        overlay = MirrorOverlay()
        overlay.init_geometry(bbox)
        overlay.sig_retranslate.connect(self._on_retranslate)
        overlay.sig_open_chat.connect(self._on_open_chat)
        self._overlays.append(overlay)
        self._current_overlay = overlay

        worker = _StreamingPipelineWorker(
            self._pipeline, capture_result, bbox,
        )
        worker.signals.ocr_done.connect(self._on_ocr_done)
        worker.signals.block_ready.connect(self._on_block_ready)
        worker.signals.finished.connect(self._on_streaming_done)
        worker.signals.error.connect(self._on_pipeline_error)
        self._current_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _run_ocr_copy(self, capture_result, bbox: tuple) -> None:
        """OCR 提取模式：OCR → 覆盖层展示原文（可选中复制）。"""
        self._loading.show_at(bbox, hint="识别中...")

        overlay = TextOverlay()
        overlay.init_geometry(bbox)
        overlay.sig_open_chat.connect(self._on_open_chat)
        self._overlays.append(overlay)
        self._current_overlay = overlay

        worker = _OcrCopyWorker(self._pipeline, capture_result)
        worker.signals.finished.connect(
            lambda blocks: self._on_ocr_copy_done(blocks, bbox),
        )
        worker.signals.error.connect(self._on_ocr_copy_error)
        self._current_worker = worker
        QThreadPool.globalInstance().start(worker)

    @pyqtSlot()
    def _on_ocr_copy_done(self, render_blocks: list, bbox: tuple) -> None:
        """OCR 提取完成 → 在覆盖层展示原文。"""
        if self._loading.isVisible():
            self._loading.dismiss_immediately()

        overlay = self._current_overlay
        if not render_blocks:
            # 未识别到文本，移除空覆盖层
            if overlay in self._overlays:
                self._overlays.remove(overlay)
                overlay.deleteLater()
            self._tray.showMessage(
                "Magic Mirror", "未识别到文本",
                QSystemTrayIcon.MessageIcon.Warning, 2000,
            )
            logger.info("OCR 提取完成，未识别到文本")
            return

        for block in render_blocks:
            overlay.add_block(block)
        logger.info("OCR 提取完成，显示 %d 个文本块", len(render_blocks))

    @pyqtSlot(str)
    def _on_ocr_copy_error(self, msg: str) -> None:
        """OCR 提取失败。"""
        if self._loading.isVisible():
            self._loading.dismiss_immediately()
        self._tray.showMessage(
            "Magic Mirror", f"文本提取失败: {msg}",
            QSystemTrayIcon.MessageIcon.Critical, 3000,
        )
        logger.error("OCR 提取失败: %s", msg)

    @pyqtSlot(list, tuple)
    def _on_ocr_done(self, text_blocks, screen_bbox: tuple) -> None:
        """OCR 完成 → 立刻关闭 loading，显示骨架占位条。"""
        # 必须立刻隐藏 loading（非动画），否则 overlay.show() 时 loading 仍可见，
        # Windows 会将 loading 设为 overlay 的 native owner，
        # loading 随后隐藏时 overlay 也被一并隐藏。
        self._loading.dismiss_immediately()
        if hasattr(self, '_current_overlay') and self._current_overlay:
            self._current_overlay.set_skeletons(text_blocks, screen_bbox)
        logger.debug("OCR 完成，显示 %d 个骨架占位条", len(text_blocks))

    @pyqtSlot(object, tuple)
    def _on_block_ready(self, render_block, screen_bbox: tuple) -> None:
        """流式渲染：每收到一个翻译块即增量显示。"""
        if hasattr(self, '_current_overlay') and self._current_overlay:
            self._current_overlay.add_block(render_block)

    @pyqtSlot(tuple)
    def _on_streaming_done(self, screen_bbox: tuple) -> None:
        # 仅在 loading 仍可见时关闭（OCR 无文本时 _on_ocr_done 不触发）
        if self._loading.isVisible():
            self._loading.dismiss_immediately()
        self._current_overlay = None
        logger.info(
            "流式翻译完成，共 %d 个覆盖层 (Esc 关闭最近 / Ctrl+Shift+Esc 关闭全部)",
            len(self._overlays),
        )

    @pyqtSlot(str)
    def _on_pipeline_error(self, msg: str) -> None:
        if self._loading.isVisible():
            self._loading.dismiss_immediately()
        self._current_overlay = None
        logger.error("翻译失败: %s", msg)

    # ── 重新翻译 ──

    @pyqtSlot(tuple)
    def _on_retranslate(self, bbox: tuple) -> None:
        """覆盖层右键菜单「重新翻译」→ 清空当前覆盖层并重跑管线。"""
        # 找到发信号的 overlay
        overlay = self.sender()
        if not isinstance(overlay, MirrorOverlay):
            return

        logger.info("重新翻译区域: %s", bbox)

        # 清空已有内容，保留 overlay 对象
        overlay._render_blocks.clear()
        overlay._skeletons.clear()
        overlay.update()

        # 截图
        try:
            capture_result = self._pipeline._capture.capture(bbox)
        except Exception as exc:
            logger.error("重新翻译截图失败: %s", exc)
            return

        self._loading.show_at(bbox)
        self._current_overlay = overlay

        worker = _StreamingPipelineWorker(
            self._pipeline, capture_result, bbox,
        )
        worker.signals.ocr_done.connect(self._on_ocr_done)
        worker.signals.block_ready.connect(self._on_block_ready)
        worker.signals.finished.connect(self._on_streaming_done)
        worker.signals.error.connect(self._on_pipeline_error)
        self._current_worker = worker
        QThreadPool.globalInstance().start(worker)

    # ── 智能对话 ──

    @pyqtSlot(str)
    def _on_open_chat(self, context_text: str) -> None:
        """覆盖层右键菜单「智能对话」→ 打开聊天窗口。"""
        dialog = ChatDialog(context_text)
        # 防止 GC 回收
        if not hasattr(self, "_chat_dialogs"):
            self._chat_dialogs: List = []
        self._chat_dialogs.append(dialog)
        dialog.finished.connect(lambda: self._chat_dialogs.remove(dialog))
        dialog.show()
        logger.info("打开智能对话窗口 (上下文 %d 字符)", len(context_text))

    # ── 系统托盘 ──

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        self._tray.setToolTip("Magic Mirror — 屏幕翻译")

        menu = QMenu()
        act_translate = QAction("翻译区域 (Ctrl+Alt+T)", menu)
        act_translate.triggered.connect(self._on_hotkey)
        menu.addAction(act_translate)

        act_ocr_copy = QAction("提取文本 (Ctrl+Alt+C)", menu)
        act_ocr_copy.triggered.connect(self._on_ocr_copy_hotkey)
        menu.addAction(act_ocr_copy)

        menu.addSeparator()

        act_close_all = QAction("关闭全部覆盖层 (Ctrl+Shift+Esc)", menu)
        act_close_all.triggered.connect(self._close_all_overlays)
        menu.addAction(act_close_all)

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

    # 让 Ctrl+C 能正常终止 Qt 应用
    signal.signal(signal.SIGINT, lambda *_: QApplication.quit())
    # Qt 事件循环需要定期返回 Python 才能处理信号
    from PyQt6.QtCore import QTimer
    _heartbeat = QTimer()
    _heartbeat.timeout.connect(lambda: None)
    _heartbeat.start(200)

    # 加载配置
    load_env()

    try:
        pipeline = create_pipeline()
    except FileNotFoundError as e:
        logger.error("配置缺失:\n%s", e)
        sys.exit(1)

    controller = StreamTranslateApp(pipeline)  # noqa: F841 — prevent GC

    # 退出时清理 listener
    app.aboutToQuit.connect(controller.cleanup)

    logger.info("Magic Mirror 已启动，按 %s 开始翻译", HOTKEY_TRIGGER)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()