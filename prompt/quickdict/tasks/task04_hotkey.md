# Task 4: 全局快捷键监听 — 实现细节

## 目标
实现全局键盘监听，检测"连按两次 Ctrl"激活取词模式，Esc 退出。

## 类设计

```python
from typing import Callable

class HotkeyListener:
    def __init__(self, on_activate: Callable, on_deactivate: Callable)
    def start(self)     # 启动监听线程
    def stop(self)      # 停止监听
    @property
    def is_active(self) -> bool  # 当前是否处于取词模式
```

## 连按 Ctrl 检测算法

```python
import time

class HotkeyListener:
    DOUBLE_PRESS_INTERVAL = 0.5  # 500ms 内连按两次

    def __init__(self, ...):
        self._ctrl_timestamps = []  # 记录 Ctrl release 的时间戳
        self._active = False

    def _on_key_release(self, key):
        if key in (Key.ctrl_l, Key.ctrl_r):
            now = time.monotonic()
            # 清理过期的时间戳
            self._ctrl_timestamps = [
                t for t in self._ctrl_timestamps
                if now - t < self.DOUBLE_PRESS_INTERVAL
            ]
            self._ctrl_timestamps.append(now)
            
            if len(self._ctrl_timestamps) >= 2:
                self._ctrl_timestamps.clear()
                self._toggle_active()

    def _on_key_press(self, key):
        if key == Key.esc and self._active:
            self._deactivate()

    def _toggle_active(self):
        if self._active:
            self._deactivate()
        else:
            self._activate()
```

## 关键设计决策

### 为什么监听 release 而非 press？
- 用户按住 Ctrl 不放时会产生多个 press 事件（键盘重复）
- 监听 release 事件更准确：一次按下-抬起算一次有效按键

### 排除 Ctrl 组合键误触
- 如果 Ctrl 和其他键同时按下（如 Ctrl+C），不计入连按次数
- 实现方式：在 `_on_key_press` 中设置 `_other_key_pressed` 标记

```python
def _on_key_press(self, key):
    if key not in (Key.ctrl_l, Key.ctrl_r):
        self._other_key_pressed = True

def _on_key_release(self, key):
    if key in (Key.ctrl_l, Key.ctrl_r):
        if self._other_key_pressed:
            self._other_key_pressed = False
            return  # 忽略组合键中的 Ctrl
        # ... 正常的连按检测逻辑
```

### 线程安全
- `pynput.keyboard.Listener` 运行在独立线程
- `on_activate` / `on_deactivate` 回调将在 pynput 线程中执行
- 回调中应通过 `QMetaObject.invokeMethod` 或 `pyqtSignal` 将事件派发到 Qt 主线程

```python
# 在 main.py 中桥接 pynput 线程和 Qt 主线程
class HotkeyBridge(QObject):
    activated = pyqtSignal()
    deactivated = pyqtSignal()

bridge = HotkeyBridge()
listener = HotkeyListener(
    on_activate=lambda: bridge.activated.emit(),
    on_deactivate=lambda: bridge.deactivated.emit()
)
```

## 独立测试方式
```python
if __name__ == '__main__':
    def on_activate():
        print("[ACTIVATED] 取词模式已开启")
    def on_deactivate():
        print("[DEACTIVATED] 取词模式已关闭")
    
    listener = HotkeyListener(on_activate, on_deactivate)
    listener.start()
    print("监听中... 连按两次 Ctrl 激活, Esc 退出, Ctrl+C 终止程序")
    try:
        import threading
        threading.Event().wait()  # 阻塞主线程
    except KeyboardInterrupt:
        listener.stop()
```
