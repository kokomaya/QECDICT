# Feature: 快速互译（选中文本 → 翻译弹窗）

## 1. 背景与目标

在任意应用中选中一段文字（中文或英文），按下热键，立刻弹出一个轻量翻译卡片，显示大模型翻译结果。  
自动检测语言方向：**中→英** 或 **英→中**，无需用户手动选择。

### 与现有模式对比

| 热键 | 模式 | 流程 |
|------|------|------|
| `Ctrl+Alt+T` | 屏幕覆盖翻译 | 框选 → 截图 → OCR → 翻译 → 覆盖渲染 |
| `Ctrl+Alt+C` | OCR 文本提取 | 框选 → 截图 → OCR → 文本弹窗 |
| `Ctrl+Alt+D` | 选中文本聊天 | 读取系统选中文本 → ChatDialog |
| **`Ctrl+Alt+E`** | **快速互译** *(新增)* | **读取系统选中文本 → 语言检测 → 翻译 → 轻量弹窗** |

---

## 2. 交互流程

```
用户选中文字（任意应用）
        ↓
    按 Ctrl+Alt+E
        ↓
  备份剪贴板内容
        ↓
  模拟 Ctrl+C（50ms等待）
        ↓
   读取选中文本
        ↓
  恢复原剪贴板内容
        ↓
   语言自动检测
   ┌────┴────┐
中文占比高    英文为主
   ↓            ↓
  中→英        英→中
        ↓
  后台调用 LLM 翻译（流式）
        ↓
  在鼠标位置附近弹出翻译卡片
  ┌──────────────────────┐
  │ 原文（折叠/截断）     │
  │ ──────────────────── │
  │ 译文（流式渐入）      │
  │ [复制译文] [复制原文] │
  └──────────────────────┘
        ↓
  点击外部 / 按 Esc → 关闭
```

**无选中文本时的回退流程：**

```
    按 Ctrl+Alt+E（无选中文本）
            ↓
    弹出「输入模式」弹窗
  ┌──────────────────────┐
  │ 输入要翻译的文字...   │  ← 可编辑输入框（自动聚焦）
  │ [翻译 ▶]  [×]        │
  └──────────────────────┘
            ↓
    用户输入文字 → 按 Enter 或点击「翻译」
            ↓
    弹窗切换为「结果模式」（同上）
```

---

## 3. 设计原则（与现有模块一致）

| 原则 | 应用方式 |
|------|---------|
| **SRP** | 语言检测、剪贴板操作、翻译调用、弹窗 UI 各自独立封装 |
| **OCP** | 新热键 + handler 追加，不修改已有 translate/ocr_copy/chat 分支 |
| **LSP** | 复用 `ITranslator` 协议，单文本翻译通过 `translate([TextBlock])` 调用 |
| **ISP** | 不引入 OCR 或框选，完全旁路 pipeline |
| **DIP** | `QuickTranslatePopup` 依赖 `ITranslator` 抽象，不直接引用 `OpenAITranslator` |

---

## 4. 语言检测方案

使用纯 Python（无额外依赖）的字符分布判断：

```python
def detect_direction(text: str) -> Literal["zh2en", "en2zh"]:
    """
    统计 CJK 字符占比。
    CJK 占比 > 20% → 中→英；否则 → 英→中。
    阈值 20% 适应混排文本（如"AI模型"）。
    """
    if not text:
        return "en2zh"
    cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return "zh2en" if cjk_count / len(text) > 0.2 else "en2zh"
```

---

## 5. Prompt 设计

在现有 `prompt_templates.py` 中新增快速互译专用模板（不修改现有覆盖翻译的 prompt）：

```python
QUICK_TRANSLATE_SYSTEM_ZH2EN = """You are a professional translator.
Translate the following Chinese text to natural, fluent English.
Output ONLY the translated text, no explanations."""

QUICK_TRANSLATE_SYSTEM_EN2ZH = """You are a professional translator.
Translate the following English text to natural, fluent Chinese (Simplified).
Output ONLY the translated text, no explanations."""
```

翻译接口：直接使用 `openai.ChatCompletion` 流式调用，不经过 `TextBlock` 批量路径（单文本无需块坐标）。

---

## 6. UI 方案

### 6.1 方案对比

| 维度 | 方案 A：复用 QuickDict PopupWidget | 方案 B：新建 QuickTranslatePopup |
|------|----------------------------------|----------------------------------|
| 开发成本 | 低（直接复用） | 中（新建但可参考） |
| 适配度 | 低——卡片结构为"单词词条"设计（phonetic/exchange 等字段），翻译场景冗余 | 高——可精确适配"原文+译文"双区块布局 |
| 流式渲染 | 不支持（设计为一次性填充） | 原生支持（直接向 QLabel/QPlainTextEdit 追加文本） |
| 原文长度 | 无法优雅处理长段落（>3行截断设计针对英文释义） | 可折叠/滚动显示原文 |
| 样式一致性 | 与 QuickDict 风格相同，与 MagicMirror 略有偏差 | 与 MagicMirror 现有 UI 风格（深色/暗色主题）保持一致 |

### 6.2 推荐：方案 B（新建 `QuickTranslatePopup`）

理由：
1. 翻译场景与词典查词场景结构差异大，强行复用会产生大量无用字段
2. 需要支持流式文本渲染（流式 token 逐字追加），QuickDict popup 无此能力
3. MagicMirror 已有成熟的 UI 基础设施（`CHAT_DIALOG_QSS`、`chat_theme.py`），可直接继承暗色主题

### 6.3 UI 结构设计

```
┌─────────────────────────────────────┐
│  ⟳  正在翻译...                [×]  │  ← 标题栏（状态指示 + 关闭按钮）
├─────────────────────────────────────┤
│  原文（折叠，最多显示 3 行）          │  ← 灰色小字，点击可展开
│  The quick brown fox jumps over...  │
├─────────────────────────────────────┤
│  译文（流式逐字显示）                 │  ← 主要内容区，白色大字
│  敏捷的棕色狐狸跳过了懒惰的狗。       │
├─────────────────────────────────────┤
│  [复制译文]        [在聊天中继续 ▶]  │  ← 操作按钮栏
└─────────────────────────────────────┘
```

弹窗有两种模式，共用同一个组件：

| 模式 | 触发条件 | 原文区 | 译文区 | 操作 |
|------|---------|--------|--------|------|
| **结果模式** | 有选中文本 | 只读折叠区 | 流式输出 | [复制译文] [在聊天中继续 ▶] |
| **输入模式** | 无选中文本 | 可编辑输入框（自动聚焦） | 空，等待提交 | [翻译 ▶] [×] |

输入模式下，用户按 `Enter`（或 `Ctrl+Enter` 支持多行）提交后，弹窗**原地切换**为结果模式，无需重新打开窗口。

- 宽度固定：420px
- 位置：鼠标光标右下方，自动避开屏幕边缘
- 动效：淡入（200ms）、流式文本追加（无闪烁）
- 主题：继承 `chat_theme.py` 暗色配色
- 关闭：点击外部区域 / `Esc` 键 / 关闭按钮

---

## 7. 影响范围

### 7.1 新增文件

| 文件 | 内容 |
|------|------|
| `magic_mirror/ui/quick_translate_popup.py` | `QuickTranslatePopup` 组件（主窗口 + 流式文本区） |
| `magic_mirror/translation/quick_translator.py` | `QuickTranslator`：单文本流式翻译 + 语言检测，依赖 `provider_factory` |

### 7.2 需修改的文件

| 文件 | 变更内容 | 风险 |
|------|---------|------|
| `magic_mirror/config/settings.py` | 新增 `HOTKEY_QUICK_TRANSLATE = "ctrl+alt+e"` | 零（仅新增常量） |
| `magic_mirror/translation/prompt_templates.py` | 新增 `QUICK_TRANSLATE_SYSTEM_ZH2EN` / `QUICK_TRANSLATE_SYSTEM_EN2ZH` | 零（仅新增常量） |
| `magic_mirror/main.py` | 新增热键注册 + `_on_quick_translate_triggered()` handler | 低（追加代码，不改已有分支） |

### 7.3 完全不修改的文件

| 文件 | 原因 |
|------|------|
| `pipeline.py` | 不经过管线 |
| `rapid_ocr_engine.py` | 无 OCR |
| `region_selector.py` | 无框选 |
| `openai_translator.py` | `QuickTranslator` 直接调用 openai client，不复用批量翻译路径 |
| `chat_dialog.py` | 无修改，但「在聊天中继续」按钮会复用 `ChatDialog` |
| `mirror_overlay.py` | 无修改 |

---

## 8. 详细实现计划

### 8.1 `settings.py` — 新增热键常量

```python
HOTKEY_QUICK_TRANSLATE = "ctrl+alt+e"   # ← 新增：选中文本快速互译
```

### 8.2 `prompt_templates.py` — 新增翻译 prompt

```python
# ── 快速互译 prompt ──────────────────────────────────────────────────
QUICK_TRANSLATE_SYSTEM_ZH2EN = (
    "You are a professional translator. "
    "Translate the following Chinese text to natural, fluent English. "
    "Output ONLY the translated text, no explanations."
)

QUICK_TRANSLATE_SYSTEM_EN2ZH = (
    "You are a professional translator. "
    "Translate the following English text to natural, fluent Chinese (Simplified). "
    "Output ONLY the translated text, no explanations."
)
```

### 8.3 `quick_translator.py` — 语言检测 + 流式翻译

```python
class QuickTranslator:
    """单文本流式翻译，自动检测中英方向。"""

    def __init__(self, provider_config: dict) -> None:
        # 通过 provider_factory 获取已配置的 openai client
        ...

    def detect_direction(self, text: str) -> Literal["zh2en", "en2zh"]:
        cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return "zh2en" if cjk_count / max(len(text), 1) > 0.2 else "en2zh"

    def translate_stream(self, text: str) -> Iterator[str]:
        """流式返回翻译 token，供 UI 逐字追加。"""
        direction = self.detect_direction(text)
        system_prompt = (
            QUICK_TRANSLATE_SYSTEM_ZH2EN if direction == "zh2en"
            else QUICK_TRANSLATE_SYSTEM_EN2ZH
        )
        # openai stream call ...
        for chunk in stream:
            if token := chunk.choices[0].delta.content:
                yield token
```

### 8.4 `quick_translate_popup.py` — UI 组件

```python
class QuickTranslatePopup(QWidget):
    """
    轻量翻译弹窗，支持两种模式：
      - 结果模式（source_text 非空）：直接展示原文 + 流式译文
      - 输入模式（source_text 为空）：展示输入框，用户提交后原地切换为结果模式

    信号:
        open_in_chat(str, str)  # (原文, 译文) → 打开 ChatDialog 继续对话
    """
    open_in_chat = pyqtSignal(str, str)

    def __init__(self, source_text: str, translator: QuickTranslator) -> None:
        # source_text 为空 → 进入输入模式
        ...

    def show_near_cursor(self) -> None:
        """在鼠标位置右下方弹出，自动避开屏幕边缘。"""
        ...

    def _switch_to_result_mode(self, text: str) -> None:
        """隐藏输入区，展示原文+译文区，启动后台翻译线程。"""
        ...

    @pyqtSlot(str)
    def append_token(self, token: str) -> None:
        """流式追加翻译 token（由后台线程通过信号调用）。"""
        ...
```

- 输入模式下，输入框自动获得焦点；`Enter` 提交（`Shift+Enter` 换行），`Esc` 关闭。
- 提交后调用 `_switch_to_result_mode(text)` 原地切换，无需销毁重建窗口。
- 后台翻译线程通过 `QRunnable` + `pyqtSignal` 将 token 推送给弹窗（与现有 `_ModelListWorker` 模式一致）。

### 8.5 `main.py` — 热键注册 + handler

```python
# ── 新增信号 ──
_sig_quick_translate = pyqtSignal()

# ── 热键注册（追加到现有注册块） ──
keyboard.add_hotkey(HOTKEY_QUICK_TRANSLATE, self._sig_quick_translate.emit)

# ── handler ──
def _on_quick_translate_triggered(self) -> None:
    text = _get_selected_text()          # 复用 chat_based_on_selected 的剪贴板方案
    # text 为空时传入空字符串 → QuickTranslatePopup 进入输入模式，不再提前返回
    popup = QuickTranslatePopup(text.strip(), self._quick_translator)
    popup.open_in_chat.connect(self._open_chat_with_context)
    popup.show_near_cursor()
```

---

## 9. 开放问题（实现前需确认）

| # | 问题 | 建议 |
|---|------|------|
| 1 | `Ctrl+Alt+E` 是否与已有软件热键冲突？ | 可配置化，从 `settings.py` 读取，支持用户覆盖 |
| 2 | 选中文本过长（>500字）时是否截断？ | 建议弹出前截断并在原文区显示"（已截断）"提示 |
| 3 | 「在聊天中继续」的上下文格式？ | `原文 + 译文` 作为 system context 传入 `ChatDialog` |
| 4 | 弹窗是否支持多显示器 DPI 缩放？ | 使用 `QScreen.devicePixelRatio()` 适配，与现有 overlay 一致 |
| 5 | 是否需要翻译历史/缓存？ | 暂不需要，保持轻量 |
