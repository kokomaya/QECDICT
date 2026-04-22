# Feature: 基于选中文本的 AI 聊天

## 1. 背景与目标

当前 Magic Mirror 提供两种模式：

| 热键 | 模式 | 流程 |
|------|------|------|
| `Ctrl+Alt+T` | 翻译 | 框选 → 截图 → OCR → 翻译 → 覆盖渲染 |
| `Ctrl+Alt+C` | 提取 | 框选 → 截图 → OCR → 文本弹窗（可复制） |

新增第三种模式：

| 热键 | 模式 | 流程 |
|------|------|------|
| `Ctrl+Alt+D` | 聊天 | 读取系统选中文本 → **直接打开 ChatDialog** |

交互方式：
1. 用户在任意应用中通过双击/拖动选中一段文字
2. 按下 `Ctrl+Alt+D`
3. 自动获取选中文本，打开 ChatDialog，文本预填入输入框

与现有 Chat 的区别：
- 现有入口：翻译覆盖层右键菜单 → 打开聊天（上下文 = 翻译结果）
- 新入口：**系统选中文本 + 热键** → 直接聊天（**无截图、无 OCR、无框选**）

## 2. 设计原则

- **开放/封闭 (OCP)**：新模式通过独立热键 + handler 实现，不修改已有 translate / ocr_copy 分支
- **单一职责 (SRP)**：选中文本获取逻辑封装为独立函数，不混入翻译/OCR 流程
- **接口隔离 (ISP)**：不涉及 IOcrEngine / ITranslator，完全独立于管线
- **依赖倒置 (DIP)**：ChatDialog 依赖 `ChatSession` 抽象，不直接耦合剪贴板操作
- **里氏替换 (LSP)**：不引入新 Worker——操作为同步（剪贴板读取 < 1ms），无需后台线程

## 3. 技术方案：获取选中文本

### 方案：模拟 Ctrl+C → 读取剪贴板

```
用户选中文本 → 按 Ctrl+Alt+D → 程序备份剪贴板 → 模拟 Ctrl+C → 读取剪贴板 → 恢复剪贴板 → 打开 ChatDialog
```

| 优点 | 缺点 |
|------|------|
| 兼容所有应用（浏览器、IDE、PDF、终端等） | 短暂覆盖剪贴板（通过备份/恢复缓解） |
| 无需额外依赖 | 极少数应用可能拦截 Ctrl+C |
| 实现简单（~20 行） | |

实现要点：
- 使用 `pyperclip` 或 `QApplication.clipboard()` 读写剪贴板
- 使用 `pynput.keyboard.Controller` 模拟 Ctrl+C（与现有 pynput 依赖一致）
- 备份 → 模拟 → 短暂等待(50ms) → 读取 → 恢复，确保不丢失用户剪贴板内容

## 4. 影响范围（最小化变更）

### 4.1 需修改的文件

| 文件 | 变更内容 | 风险 |
|------|---------|------|
| `magic_mirror/config/settings.py` | 新增 `HOTKEY_CHAT = "Ctrl+Alt+D"` | 零（仅新增常量） |
| `magic_mirror/main.py` | 新增热键注册 + handler + 剪贴板获取逻辑 | 低（追加代码，不改已有分支） |

### 4.2 完全不修改的文件

| 文件 | 原因 |
|------|------|
| `pipeline.py` | 不涉及管线 |
| `rapid_ocr_engine.py` | 不涉及 OCR |
| `region_selector.py` | 不涉及框选 |
| `chat_service.py` | 已有 `ChatSession(context_text, model)` 完全满足 |
| `chat_dialog.py` | 已有 `ChatDialog(context_text)` 完全满足 |
| `ui/*.py` | 不涉及 |

## 5. 详细实现计划

### 5.1 settings.py — 新增热键常量

```python
# ── 热键 ──
HOTKEY_TRIGGER = "ctrl+alt+t"
HOTKEY_OCR_COPY = "ctrl+alt+c"
HOTKEY_CHAT = "Ctrl+Alt+D"             # ← 新增：选中文本后直接 AI 聊天
```

### 5.2 main.py — 新增热键 + handler

#### 5.2.1 导入

```python
from magic_mirror.config.settings import HOTKEY_OCR_COPY, HOTKEY_TRIGGER, HOTKEY_CHAT
```

#### 5.2.2 信号声明

在 `StreamTranslateApp` 类级别：

```python
_sig_chat_triggered = pyqtSignal()
```

#### 5.2.3 热键注册

在 `__init__` 中：

```python
self._chat_labels = _parse_hotkey(HOTKEY_CHAT)
self._sig_chat_triggered.connect(self._on_chat_hotkey)
```

在 `on_press` 中追加：

```python
elif self._chat_labels.issubset(self._pressed_labels):
    self._pressed_labels.clear()
    self._sig_chat_triggered.emit()
```

#### 5.2.4 获取选中文本

```python
def _grab_selected_text(self) -> str:
    """模拟 Ctrl+C 获取系统当前选中文本，完成后恢复剪贴板。"""
    from pynput.keyboard import Controller, Key
    import time

    clipboard = QApplication.clipboard()
    backup = clipboard.text()          # 备份当前剪贴板

    kb = Controller()
    kb.press(Key.ctrl)
    kb.press('c')
    kb.release('c')
    kb.release(Key.ctrl)

    time.sleep(0.05)                   # 等待系统完成复制

    selected = clipboard.text()
    clipboard.setText(backup)          # 恢复剪贴板

    # 如果剪贴板内容没变化，说明没有选中文本
    if selected == backup:
        return ""
    return selected.strip()
```

#### 5.2.5 热键 handler

```python
@pyqtSlot()
def _on_chat_hotkey(self) -> None:
    text = self._grab_selected_text()
    if not text:
        self._tray.showMessage(
            "Magic Mirror", "未检测到选中文本",
            QSystemTrayIcon.MessageIcon.Warning, 2000,
        )
        return
    self._open_chat_dialog(text)
```

> `_open_chat_dialog` 即已有的 `_on_open_chat` 方法，直接复用。

#### 5.2.6 系统托盘菜单

在托盘菜单中现有项后追加：

```python
chat_action = QAction("AI 聊天 (Ctrl+Alt+D)", menu)
chat_action.triggered.connect(self._on_chat_hotkey)
```

## 6. 数据流对比

```
翻译模式:  框选 → 截图 → OCR → 段落合并 → LLM翻译 → 排版 → 覆盖渲染  (~17s)
提取模式:  框选 → 截图 → OCR → 排版(伪翻译) → TextOverlay            (~5s)
聊天模式:  选中文本 → Ctrl+Alt+D → 读剪贴板 → ChatDialog              (~50ms)
                                                ↑ 无截图/OCR/翻译/排版
```

## 7. 实现步骤

| # | 任务 | 文件 | 预计行数 |
|---|------|------|---------|
| 1 | 新增 `HOTKEY_CHAT` 常量 | `settings.py` | +1 |
| 2 | 新增 `import HOTKEY_CHAT` | `main.py` | +1 |
| 3 | 声明 `_sig_chat_triggered` 信号 | `main.py` 类变量 | +1 |
| 4 | `__init__` 中解析热键 + 连接信号 | `main.py` | +2 |
| 5 | `on_press` 中追加热键匹配分支 | `main.py` | +3 |
| 6 | 新增 `_grab_selected_text` 方法 | `main.py` | +18 |
| 7 | 新增 `_on_chat_hotkey` handler | `main.py` | +8 |
| 8 | 托盘菜单追加 "AI 聊天" | `main.py` | +2 |
| **合计** | | **2 文件** | **~+36 行** |

## 8. 风险与回退

| 风险 | 缓解措施 |
|------|---------|
| 热键冲突 | `Ctrl+Alt+D` 无常见系统/IDE 占用；可在 settings.py 自定义 |
| 模拟 Ctrl+C 覆盖剪贴板 | 备份 → 复制 → 读取 → 恢复，用户无感知 |
| 部分应用拦截 Ctrl+C（如终端） | 属于极端边界场景，用户可手动复制后使用 |
| 选中文本为空 | 检测并提示"未检测到选中文本" |
| 配置缺失 (无 LLM) | ChatDialog 内部会处理 API 错误并显示错误消息 |

## 9. 后续扩展（不在本次范围）

- 支持富文本选中（保留格式）
- 聊天历史持久化
- 支持图片作为聊天上下文（多模态 LLM）
- 支持自定义系统 prompt 模板
