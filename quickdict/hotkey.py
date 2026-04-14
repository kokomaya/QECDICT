"""
hotkey.py — 全局快捷键监听。

职责单一：检测键盘事件（连按 Ctrl 激活 / Esc 退出），通过回调通知外部。
不含任何 UI 逻辑，可独立运行测试。
"""
import time
from typing import Callable

from pynput.keyboard import Key, Listener


class HotkeyListener:
    """
    全局键盘监听器。

    - 500ms 内连按两次 Ctrl（左/右均可）→ 切换取词模式
    - 取词模式下按 Esc → 退出取词模式
    - Ctrl 组合键（如 Ctrl+C）不触发激活
    - 取词模式下单次 Ctrl 释放 → 触发 on_ctrl_capture（供 Ctrl 取词模式使用）
    """

    DOUBLE_PRESS_INTERVAL = 0.5  # 秒

    def __init__(self, on_activate: Callable, on_deactivate: Callable,
                 on_ctrl_capture: Callable | None = None):
        self._on_activate = on_activate
        self._on_deactivate = on_deactivate
        self._on_ctrl_capture = on_ctrl_capture
        self._active = False
        self._ctrl_release_times: list[float] = []
        self._other_key_pressed = False
        self._listener: Listener | None = None

    # ── 公开接口 ──────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self):
        """启动监听（在独立守护线程中运行）。"""
        if self._listener is not None:
            return
        self._listener = Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        """停止监听。"""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    # ── 键盘事件处理 ──────────────────────────────────────

    def _on_key_press(self, key):
        # Esc 退出取词模式
        if key == Key.esc and self._active:
            self._deactivate()
            return

        # 记录是否有非 Ctrl 键按下（用于排除组合键）
        if key not in (Key.ctrl_l, Key.ctrl_r):
            self._other_key_pressed = True

    def _on_key_release(self, key):
        if key not in (Key.ctrl_l, Key.ctrl_r):
            return

        # 组合键中的 Ctrl 释放 → 不计入连按
        if self._other_key_pressed:
            self._other_key_pressed = False
            self._ctrl_release_times.clear()
            return

        now = time.monotonic()

        # 清除过期时间戳，保留窗口期内的
        self._ctrl_release_times = [
            t for t in self._ctrl_release_times
            if now - t < self.DOUBLE_PRESS_INTERVAL
        ]
        self._ctrl_release_times.append(now)

        # 检测双击
        if len(self._ctrl_release_times) >= 2:
            self._ctrl_release_times.clear()
            self._toggle()
            return

        # 取词模式已激活 + 单次 Ctrl → 触发 Ctrl 取词回调
        if self._active and self._on_ctrl_capture:
            self._on_ctrl_capture()

    # ── 状态切换 ──────────────────────────────────────────

    def _toggle(self):
        if self._active:
            self._deactivate()
        else:
            self._activate()

    def _activate(self):
        if self._active:
            return
        self._active = True
        self._on_activate()

    def _deactivate(self):
        if not self._active:
            return
        self._active = False
        self._on_deactivate()


# ── 独立运行测试 ──────────────────────────────────────────
if __name__ == "__main__":
    import threading

    def on_activate():
        print("[ACTIVATED] 取词模式已开启")

    def on_deactivate():
        print("[DEACTIVATED] 取词模式已关闭")

    listener = HotkeyListener(on_activate, on_deactivate)
    listener.start()
    print("监听中... 连按两次 Ctrl 激活/关闭, Esc 退出取词模式, Ctrl+C 终止程序")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        listener.stop()
        print("\n已退出")
