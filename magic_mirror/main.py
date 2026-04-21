"""主程序集成 — 组装所有组件，串联 UI 交互与翻译管线。

Composition Root：这是整个项目中唯一 import 具体实现类的地方。
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import List, Tuple

from PyQt6.QtCore import QObject, QRect, QRunnable, QThreadPool, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from magic_mirror.config import load_env, load_llm_config
from magic_mirror.config.settings import HOTKEY_CHAT, HOTKEY_OCR_COPY, HOTKEY_TRIGGER
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


def create_pipeline_ocr_only() -> TranslatePipeline:
    """创建仅 OCR 的管线（翻译不可用时的降级方案）。"""
    from magic_mirror.interfaces.types import TranslatedBlock

    class _NoOpTranslator:
        def translate(self, blocks):
            return [TranslatedBlock(source=b, translated_text=b.text) for b in blocks]
        def translate_stream(self, blocks):
            yield from self.translate(blocks)

    return TranslatePipeline(
        capture=PilScreenCapture(),
        ocr=RapidOcrEngine(),
        translator=_NoOpTranslator(),
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
    _sig_chat_triggered = pyqtSignal()           # 选中文本 AI 聊天
    _sig_close_last_overlay = pyqtSignal()      # Esc 关闭最近一个覆盖层
    _sig_close_all_overlays = pyqtSignal()      # Ctrl+Shift+Esc 关闭全部

    # 框选完成后的操作模式
    _MODE_TRANSLATE = "translate"
    _MODE_OCR_COPY = "ocr_copy"

    def __init__(self, pipeline: TranslatePipeline, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._pipeline = pipeline
        self._pending_mode = self._MODE_TRANSLATE
        self._config_error: str | None = None

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
        self._chat_labels = _parse_hotkey(HOTKEY_CHAT)
        self._pressed_labels: set = set()
        logger.debug("注册热键: %s → %s, %s → %s, %s → %s",
                     HOTKEY_TRIGGER, self._hotkey_labels,
                     HOTKEY_OCR_COPY, self._ocr_copy_labels,
                     HOTKEY_CHAT, self._chat_labels)
        self._sig_chat_triggered.connect(self._on_chat_hotkey)
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
            # Ctrl+Alt+Q → 选中文本 AI 聊天
            elif self._chat_labels.issubset(self._pressed_labels):
                logger.info("热键匹配! 触发 AI 聊天")
                self._pressed_labels.clear()
                self._sig_chat_triggered.emit()
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

    def set_config_error(self, msg: str) -> None:
        """标记 LLM 配置缺失，启动后通过托盘提示用户。"""
        self._config_error = msg
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1000, self._show_config_hint)

    def _show_config_hint(self) -> None:
        self._tray.showMessage(
            "Magic Mirror",
            "LLM not configured — translate disabled.\n"
            "Place llm_providers.yaml next to exe.\n"
            "OCR text extraction (Ctrl+Alt+C) still works.",
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )

    @pyqtSlot()
    def _on_hotkey(self) -> None:
        """翻译热键触发 → 启动框选。"""
        if self._config_error:
            self._tray.showMessage(
                "Magic Mirror",
                "Translation unavailable — LLM not configured.\n"
                "Place llm_providers.yaml and .env next to the exe.",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
            return
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
        # 按原文位置重排预览面板
        if hasattr(self, '_current_overlay') and self._current_overlay:
            self._current_overlay.finalize_preview()
        self._current_overlay = None
        logger.info(
            "流式翻译完成，共 %d 个覆盖层 (Esc 关闭最近 / Ctrl+Shift+Esc 关闭全部)",
            len(self._overlays),
        )

    @pyqtSlot(str)
    def _on_pipeline_error(self, msg: str) -> None:
        if self._loading.isVisible():
            self._loading.dismiss_immediately()
        if hasattr(self, '_current_overlay') and self._current_overlay:
            self._current_overlay.show_error("翻译失败，右键重试")
        self._current_overlay = None
        self._tray.showMessage(
            "Magic Mirror", f"翻译失败: {msg}",
            QSystemTrayIcon.MessageIcon.Critical, 3000,
        )
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
        overlay._preview.clear_texts()
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

    # ── 选中文本 AI 聊天 ──

    @pyqtSlot()
    def _on_chat_hotkey(self) -> None:
        """Ctrl+Alt+Q → 延迟后获取系统选中文本，打开聊天对话框。

        延迟 300ms 等待用户松开所有物理按键，避免：
        1. 残留 Ctrl/Alt 干扰模拟的 Ctrl+C
        2. Ctrl 释放被 quickdict 双击检测误捕获
        """
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, self._do_grab_and_chat)

    @pyqtSlot()
    def _do_grab_and_chat(self) -> None:
        """延迟回调：获取选中文本并打开聊天（预填入输入框）。"""
        try:
            text = self._grab_selected_text()
            if not text:
                self._tray.showMessage(
                    "Magic Mirror", "未检测到选中文本",
                    QSystemTrayIcon.MessageIcon.Warning, 2000,
                )
                return
            logger.info("grabbed text (%d chars), creating ChatDialog...", len(text))
            dialog = ChatDialog(context_text="", prefill=text)
            logger.info("ChatDialog created, storing ref and showing...")
            if not hasattr(self, "_chat_dialogs"):
                self._chat_dialogs: List = []
            self._chat_dialogs.append(dialog)
            dialog.finished.connect(lambda: self._chat_dialogs.remove(dialog))
            dialog.show()
            logger.info("打开 AI 聊天窗口 (预填 %d 字符)", len(text))
        except Exception:
            logger.exception("_do_grab_and_chat crashed")

    @staticmethod
    def _grab_selected_text() -> str:
        """通过 Win32 keybd_event 模拟 Ctrl+C，从前台窗口获取选中文本。

        使用 keybd_event 直接向前台窗口发送按键（比 SendInput 简单可靠）。
        使用 win32 原生剪贴板 API，避免 Qt OleSetClipboard COM 锁冲突。
        """
        import ctypes
        import time

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 64 位系统必须设置正确的参数/返回类型，否则指针被截断
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        user32.GetClipboardData.restype = ctypes.c_void_p
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

        KEYEVENTF_KEYUP = 0x0002
        VK_CONTROL = 0x11
        VK_MENU = 0x12      # Alt
        VK_C = 0x43
        CF_UNICODETEXT = 13

        # ── 剪贴板读写 ──
        def _get_clipboard() -> str:
            for _ in range(5):
                if user32.OpenClipboard(0):
                    try:
                        h = user32.GetClipboardData(CF_UNICODETEXT)
                        if not h:
                            return ""
                        p = kernel32.GlobalLock(h)
                        if not p:
                            return ""
                        try:
                            return ctypes.wstring_at(p)
                        finally:
                            kernel32.GlobalUnlock(h)
                    finally:
                        user32.CloseClipboard()
                    break
                time.sleep(0.02)  # 剪贴板被占用，短暂重试
            return ""

        def _set_clipboard(text: str) -> None:
            for _ in range(5):
                if user32.OpenClipboard(0):
                    try:
                        user32.EmptyClipboard()
                        buf = (text + "\0").encode("utf-16-le")
                        h = kernel32.GlobalAlloc(0x0002, len(buf))
                        if not h:
                            return
                        p = kernel32.GlobalLock(h)
                        if not p:
                            return
                        ctypes.memmove(p, buf, len(buf))
                        kernel32.GlobalUnlock(h)
                        user32.SetClipboardData(CF_UNICODETEXT, h)
                    finally:
                        user32.CloseClipboard()
                    return
                time.sleep(0.02)

        # ── 执行 ──
        backup = _get_clipboard()

        # 确保修饰键已释放（物理键可能刚松开但 OS 状态还没更新）
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)     # Alt ↑
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)  # Ctrl ↑
        time.sleep(0.05)

        # 模拟 Ctrl+C
        user32.keybd_event(VK_CONTROL, 0, 0, 0)                # Ctrl ↓
        user32.keybd_event(VK_C, 0, 0, 0)                      # C ↓
        user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)        # C ↑
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)  # Ctrl ↑

        time.sleep(0.2)  # 等待前台应用完成复制

        selected = _get_clipboard()

        # 恢复剪贴板
        if selected != backup:
            _set_clipboard(backup)

        if selected == backup:
            return ""
        return selected.strip()

    # ── 系统托盘 ──

    @staticmethod
    def _create_tray_icon() -> QIcon:
        """生成 Magic Mirror 托盘图标（程序化绘制，无需外部图片）。"""
        size = 32
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 圆形底色（品牌蓝）
        p.setBrush(QColor(0, 120, 215))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, size - 2, size - 2)

        # 中央 "M" 字母
        font = QFont("Segoe UI", 17)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "M")

        p.end()
        return QIcon(pm)

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._create_tray_icon())
        self._tray.setToolTip("Magic Mirror — 屏幕翻译")

        menu = QMenu()
        act_translate = QAction("翻译区域 (Ctrl+Alt+T)", menu)
        act_translate.triggered.connect(self._on_hotkey)
        menu.addAction(act_translate)

        act_ocr_copy = QAction("提取文本 (Ctrl+Alt+C)", menu)
        act_ocr_copy.triggered.connect(self._on_ocr_copy_hotkey)
        menu.addAction(act_ocr_copy)

        act_chat = QAction("AI 聊天 (Ctrl+Alt+D)", menu)
        act_chat.triggered.connect(self._on_chat_hotkey)
        menu.addAction(act_chat)

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

    config_err = None
    try:
        pipeline = create_pipeline()
    except (FileNotFoundError, KeyError, ValueError) as e:
        logger.warning("LLM config not ready (translation disabled): %s", e)
        config_err = str(e)
        pipeline = create_pipeline_ocr_only()

    controller = StreamTranslateApp(pipeline)  # noqa: F841 — prevent GC

    if config_err:
        controller.set_config_error(config_err)

    # 退出时清理 listener
    app.aboutToQuit.connect(controller.cleanup)

    logger.info("Magic Mirror 已启动，按 %s 开始翻译", HOTKEY_TRIGGER)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()