# StreamTranslate — 魔法镜子实时屏幕翻译

## 概述

用户可以像截图一样框选屏幕上的一块区域，系统对该区域进行 OCR 识别英文内容，调用 AI 模型翻译为中文，然后将翻译后的中文**原位覆盖**回屏幕上，保持与原文完全一致的排版、字号、位置和格式。效果就像一面"魔法镜子"——镜子照过的地方，英文全部变成了中文。

## 核心概念

```
┌─────────────────────────────────────────────┐
│              用户屏幕 (English)              │
│                                             │
│   ┌───────────────────────┐                 │
│   │  The quick brown fox  │  ← 用户框选区域  │
│   │  jumps over the lazy  │                 │
│   │  dog.                 │                 │
│   └───────────────────────┘                 │
│                    ↓                        │
│   ┌───────────────────────┐                 │
│   │  敏捷的棕色狐狸跳过了  │  ← 魔法镜子覆盖  │
│   │  懒惰的狗。            │     (原位渲染)    │
│   └───────────────────────┘                 │
└─────────────────────────────────────────────┘
```

**关键区分：** 这不是一个翻译弹窗，而是一个**覆盖层**——在原位置用中文替换英文显示，尽量还原原始排版。

---

## 设计原则 — SOLID

本项目严格遵循 SOLID 原则，确保各模块职责清晰、易于扩展和测试。

| 原则 | 应用方式 |
|------|---------|
| **S — 单一职责** | 每个模块/类只做一件事：截图、OCR、翻译、排版、渲染各自独立，互不侵入 |
| **O — 开闭原则** | 通过抽象协议 (Protocol) 定义核心接口；新增 OCR 引擎或翻译后端只需新增实现类，无需修改调用方 |
| **L — 里氏替换** | 所有 `ITranslator` / `IOcrEngine` / `IScreenCapture` 的实现可互相替换，行为契约一致 |
| **I — 接口隔离** | 接口按职责拆分：翻译接口不包含 OCR 方法，截图接口不包含渲染逻辑 |
| **D — 依赖倒置** | 高层模块 (`TranslatePipeline`) 依赖抽象协议而非具体类；具体实现通过工厂/配置注入 |

---

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| GUI 框架 | PyQt6 | 与 QuickDict 主项目一致 |
| 屏幕截图 | PIL.ImageGrab + dxcam (fallback) | 复用 QuickDict 已有能力 |
| OCR 引擎 | RapidOCR (rapidocr-onnxruntime) | 复用 QuickDict 已有能力，需要获取**带坐标的文本块** |
| AI 翻译 | OpenAI 兼容接口 (可替换后端) | 通过抽象协议隔离，具体后端由配置决定 |
| 覆盖渲染 | PyQt6 无边框透明窗口 | 在屏幕上精确覆盖翻译后文本 |
| 全局热键 | pynput | 复用 QuickDict 已有能力 |

---

## 项目结构

```
magic_mirror/
│
├── __init__.py
├── main.py                      # 入口 & 应用控制器 (编排层)
│
├── config/                      # ── 配置层 (D: 依赖倒置 — 外部化所有可变项) ──
│   ├── __init__.py
│   ├── settings.py              # 应用通用配置 (热键, UI, OCR 参数等)
│   ├── llm_providers.yaml       # 🔒 LLM 后端配置 (URL/模型/header)，不入库
│   └── .env                     # 🔒 敏感凭证 (API_TOKEN 等)，不入库
│
├── interfaces/                  # ── 抽象协议层 (O+L+I: 面向接口编程) ──
│   ├── __init__.py
│   ├── types.py                 # 共享数据模型 (TextBlock, RenderBlock 等)
│   ├── i_screen_capture.py      # Protocol: IScreenCapture
│   ├── i_ocr_engine.py          # Protocol: IOcrEngine
│   ├── i_translator.py          # Protocol: ITranslator
│   └── i_layout_engine.py       # Protocol: ILayoutEngine
│
├── capture/                     # ── 屏幕采集层 (S: 截图职责独立) ──
│   ├── __init__.py
│   ├── region_selector.py       # 鼠标拖拽框选 UI
│   └── pil_capture.py           # IScreenCapture 实现: PIL + dxcam fallback
│
├── ocr/                         # ── OCR 识别层 (S: OCR 职责独立) ──
│   ├── __init__.py
│   ├── rapid_ocr_engine.py      # IOcrEngine 实现: RapidOCR
│   └── preprocess.py            # 图像预处理变体 (CLAHE, 二值化等)
│
├── translation/                 # ── 翻译层 (O+D: 后端可替换) ──
│   ├── __init__.py
│   ├── openai_translator.py     # ITranslator 实现: OpenAI 兼容接口
│   ├── prompt_templates.py      # 翻译 Prompt 模板 (与后端解耦)
│   └── provider_factory.py      # 工厂：根据配置创建 ITranslator 实例
│
├── layout/                      # ── 排版层 (S: 排版计算独立) ──
│   ├── __init__.py
│   ├── layout_engine.py         # ILayoutEngine 实现: 坐标映射 + 字号适配
│   └── color_sampler.py         # 背景/前景色采样 (从截图提取)
│
├── ui/                          # ── 渲染层 (S: UI 渲染独立) ──
│   ├── __init__.py
│   ├── mirror_overlay.py        # 魔法镜子覆盖窗口
│   └── loading_indicator.py     # 翻译等待动画
│
├── pipeline.py                  # ── 管线编排 (D: 依赖抽象协议组装流程) ──
│
└── requirements.txt
```

### 配置隔离说明

所有 LLM 后端相关的 **URL、IP、端口、模型名称、认证头** 均从代码中剥离，集中在 `config/` 目录下管理：

| 文件 | 内容 | 是否入库 |
|------|------|---------|
| `config/.env` | `API_TOKEN`, `API_USERNAME` 等敏感凭证 | ❌ `.gitignore` |
| `config/llm_providers.yaml` | 后端 URL、模型列表、自定义 Header、租户 ID 等 | ❌ `.gitignore` |
| `config/llm_providers.example.yaml` | 脱敏示例配置，供团队参考 | ✅ 入库 |
| `config/settings.py` | 通用配置（热键、UI 参数、OCR 阈值） | ✅ 入库 |

---

## 抽象接口定义

### `interfaces/types.py` — 共享数据模型

```python
from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class TextBlock:
    """OCR 识别出的单个文本块"""
    text: str                                        # 识别的文本
    bbox: List[List[float]]                          # 四角坐标 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    font_size_est: float                             # 估算字号 (基于 bbox 高度)
    confidence: float                                # OCR 置信度

@dataclass
class TranslatedBlock:
    """翻译后的文本块 = TextBlock + 译文"""
    source: TextBlock
    translated_text: str                             # 翻译后的文本

@dataclass
class RenderBlock:
    """可渲染的文本块 = 屏幕坐标 + 渲染参数"""
    screen_x: int
    screen_y: int
    width: int
    height: int
    translated_text: str
    font_size: int
    bg_color: Tuple[int, int, int, int]              # RGBA
    text_color: Tuple[int, int, int]                 # RGB

@dataclass
class CaptureResult:
    """截图结果"""
    image: object                                    # np.ndarray (BGR)
    screen_bbox: Tuple[int, int, int, int]           # (x, y, w, h) 屏幕绝对坐标
```

### `interfaces/i_screen_capture.py`

```python
from typing import Protocol, Tuple
from .types import CaptureResult

class IScreenCapture(Protocol):
    """屏幕截图协议 — 对指定矩形区域截图"""
    def capture(self, bbox: Tuple[int, int, int, int]) -> CaptureResult:
        """bbox: (x, y, w, h) 屏幕坐标 → 截图结果"""
        ...
```

### `interfaces/i_ocr_engine.py`

```python
from typing import Protocol, List
import numpy as np
from .types import TextBlock

class IOcrEngine(Protocol):
    """OCR 识别协议 — 从图像中提取带位置信息的文本块"""
    def recognize(self, image: np.ndarray) -> List[TextBlock]:
        ...
```

### `interfaces/i_translator.py`

```python
from typing import Protocol, List
from .types import TextBlock, TranslatedBlock

class ITranslator(Protocol):
    """翻译协议 — 将文本块批量翻译"""
    def translate(self, blocks: List[TextBlock]) -> List[TranslatedBlock]:
        ...
```

### `interfaces/i_layout_engine.py`

```python
from typing import Protocol, List, Tuple
import numpy as np
from .types import TranslatedBlock, RenderBlock

class ILayoutEngine(Protocol):
    """排版协议 — 将翻译结果映射为可渲染块"""
    def compute_layout(
        self,
        blocks: List[TranslatedBlock],
        screenshot: np.ndarray,
        screen_bbox: Tuple[int, int, int, int],
    ) -> List[RenderBlock]:
        ...
```

---

## 管线编排 — `pipeline.py`

管线编排层 **只依赖抽象协议**，不 import 任何具体实现类（依赖倒置）。

```python
class TranslatePipeline:
    """
    翻译管线 — 串联 截图→OCR→翻译→排版 全流程。
    所有组件通过构造函数注入 (D: 依赖倒置)。
    """
    def __init__(
        self,
        capture: IScreenCapture,
        ocr: IOcrEngine,
        translator: ITranslator,
        layout: ILayoutEngine,
    ):
        self._capture = capture
        self._ocr = ocr
        self._translator = translator
        self._layout = layout

    def execute(self, bbox: Tuple[int, int, int, int]) -> List[RenderBlock]:
        # 1. 截图
        result = self._capture.capture(bbox)
        # 2. OCR 识别
        blocks = self._ocr.recognize(result.image)
        # 3. 翻译
        translated = self._translator.translate(blocks)
        # 4. 计算排版
        return self._layout.compute_layout(translated, result.image, result.screen_bbox)
```

---

## 模块设计

### M1: `capture/region_selector.py` — 区域框选

**职责 (S)**：全屏半透明遮罩，鼠标拖拽框选目标区域，仅负责 UI 交互，不涉及截图。

- 全屏透明覆盖层 (`QWidget`, `FramelessWindowHint | WindowStaysOnTopHint`)
- 鼠标按下 → 记录起点；拖动 → 绘制矩形虚线框；释放 → 发射 `Signal(QRect)`
- 按 Esc 取消框选
- 支持多显示器 (合并虚拟桌面几何)
- **不依赖**任何业务接口 — 纯 UI 组件

### M2: `capture/pil_capture.py` — `IScreenCapture` 实现

**职责 (S)**：实现 `IScreenCapture` 协议，对指定区域截图。

- 主路径：`PIL.ImageGrab.grab(bbox)`
- 备选：`dxcam` (硬件加速窗口截图黑屏时 fallback)
- DPI 感知，物理像素坐标对齐
- **可替换**：未来可新增 `DxcamCapture` 等实现 (O: 开闭原则)

### M3: `ocr/rapid_ocr_engine.py` — `IOcrEngine` 实现

**职责 (S)**：实现 `IOcrEngine` 协议，从图像提取带坐标的文本块。

- 使用 RapidOCR 的 `__call__` 接口：
  ```python
  results = ocr(img)
  # results: list of [bbox_points, text, confidence]
  ```
- 对每个文本块构建 `TextBlock` 数据对象
- 预处理委托给 `ocr/preprocess.py`（S: 预处理是独立职责）
- 过滤低置信度结果
- **可替换**：未来可新增 `TesseractOcrEngine`, `WindowsOcrEngine` 等 (O)

### `ocr/preprocess.py` — 图像预处理

**职责 (S)**：生成多种预处理变体，提升 OCR 识别率。独立于 OCR 引擎本身。

- 8 种变体：原图、CLAHE、Otsu 二值化、自适应阈值、形态学、2x 放大、放大+锐化、放大+CLAHE
- 输入/输出纯 `np.ndarray`，不依赖任何 OCR 库

### M4: `translation/openai_translator.py` — `ITranslator` 实现

**职责 (S)**：实现 `ITranslator` 协议，调用 OpenAI 兼容 API 进行批量翻译。

- 从 `config/llm_providers.yaml` 读取后端配置（URL、模型、Header）
- 从 `config/.env` 读取凭证 (`API_TOKEN`)
- **代码中不出现任何硬编码的 URL / IP / 模型名**
- Prompt 模板来自 `translation/prompt_templates.py` (S: Prompt 管理独立)
- 支持 streaming 模式（可选）
- 请求/响应均为 JSON，批量翻译一次 API 调用
- **可替换**：未来可新增 `AzureTranslator`, `GoogleTranslator` 等 (O)

### `translation/prompt_templates.py` — Prompt 模板

**职责 (S)**：集中管理所有 AI Prompt，与翻译后端实现解耦。

```python
SYSTEM_PROMPT = """你是一个专业的英中翻译引擎，专门用于屏幕文本的实时翻译。

规则：
1. 将输入的英文文本翻译为简体中文
2. 输入是一组带编号的文本片段，来自屏幕截图的 OCR 识别
3. 保持编号一一对应，逐条翻译
4. 翻译要求自然、简洁，符合中文表达习惯
5. UI 元素（按钮、菜单）翻译要简短精炼
6. 专有名词保持英文原文（如 Python, GitHub, Windows）
7. 如果某条文本不是有意义的英文（如乱码、符号），原样返回
8. 严格以 JSON 数组格式输出：[{"id": 1, "zh": "..."}, ...]"""

def build_user_prompt(texts: list[tuple[int, str]]) -> str:
    """构建用户 Prompt: [(id, text), ...] → 编号文本列表"""
    lines = ["请翻译以下文本："]
    for idx, text in texts:
        lines.append(f"{idx}. {text}")
    return "\n".join(lines)
```

### `translation/provider_factory.py` — 翻译后端工厂

**职责 (S+D)**：根据配置文件创建 `ITranslator` 实例。调用方无需知道具体后端类型。

```python
def create_translator(provider_config: dict) -> ITranslator:
    """
    根据 provider_config["type"] 创建对应的 ITranslator 实例。
    支持: "openai_compatible" (默认), 未来可扩展更多类型。
    """
    ...
```

### M5: `layout/layout_engine.py` — `ILayoutEngine` 实现

**职责 (S)**：实现 `ILayoutEngine` 协议，将翻译结果映射为可渲染块。

- 根据原始 `bbox` → 屏幕绝对坐标
- 字号估算 + 中文字符宽度补偿
- 溢出处理：缩小字号 → 轻微水平扩展
- 颜色提取委托给 `layout/color_sampler.py` (S)

### `layout/color_sampler.py` — 颜色采样

**职责 (S)**：从截图中提取文本块的背景色和前景色。独立于排版逻辑。

- 背景色：bbox 周围区域中值模糊 + 众数提取
- 前景色：bbox 内文字区域主色调 / 与背景反色

### M6: `ui/mirror_overlay.py` — 魔法镜子覆盖窗口

**职责 (S)**：接收 `List[RenderBlock]` 并渲染到屏幕上。纯 UI 组件，不涉及业务逻辑。

- 无边框透明窗口 (`FramelessWindowHint | WindowStaysOnTopHint | Tool`)
- `QPainter` 逐块绘制：背景色矩形 + 中文文字
- 可选：截图作为底图 + 仅覆盖文字区域
- 交互：Esc 关闭、可穿透鼠标 (`WA_TransparentForMouseEvents`)、右键菜单
- **只接收数据，不调用任何业务模块** (I: 接口隔离)

### `ui/loading_indicator.py` — 加载动画

**职责 (S)**：翻译等待时显示的加载指示器。独立 UI 组件。

### M7: `main.py` — 应用控制器

**职责**：唯一的"组装点"——创建具体实现、注入到管线、连接 UI 信号。

```python
# main.py — 组装 (Composition Root)
def create_pipeline(config) -> TranslatePipeline:
    """根据配置组装管线 — 具体类只在此处出现"""
    capture = PilScreenCapture()
    ocr = RapidOcrEngine(config.ocr)
    translator = create_translator(config.llm_provider)
    layout = DefaultLayoutEngine()
    return TranslatePipeline(capture, ocr, translator, layout)
```

- 全局热键注册（`Ctrl+Alt+T`）触发框选
- 信号流：`RegionSelector.selected → pipeline.execute → MirrorOverlay.render`
- 系统托盘图标 + 右键菜单

---

## 配置文件规范

### `config/llm_providers.example.yaml` （入库 — 脱敏示例）

```yaml
# LLM 后端配置示例
# 复制为 llm_providers.yaml 并填入实际值

default_provider: "my_provider"

providers:
  my_provider:
    type: "openai_compatible"
    base_url: "https://your-api-endpoint:port"     # 替换为实际 URL
    model: "your-model-name"                        # 替换为实际模型
    headers:
      useLegacyCompletionsEndpoint: "false"
      X-Tenant-ID: "default_tenant"                 # 替换为实际租户
    timeout: 60
    max_retries: 2
    stream: false                                   # 是否启用 streaming
```

### `config/.env` （不入库 — 凭证）

```env
# API 凭证 — 不要提交到版本库
API_TOKEN=your_api_token_here
API_USERNAME=your_username_here
```

### `config/settings.py` （入库 — 通用配置）

```python
"""应用通用配置 — 不包含任何后端 URL / IP / 凭证"""

# 热键
HOTKEY_TRIGGER = "ctrl+alt+t"

# OCR
OCR_CONFIDENCE_THRESHOLD = 0.5
OCR_DET_BOX_THRESH = 0.3

# UI
OVERLAY_OPACITY = 255                   # 覆盖层不透明度 (0-255)
SELECTOR_MASK_COLOR = (0, 0, 0, 80)     # 框选遮罩颜色 RGBA
SELECTOR_BORDER_COLOR = (0, 120, 215)   # 框选边框颜色 RGB

# 排版
FONT_FAMILY_ZH = "Microsoft YaHei"     # 中文字体
FONT_SIZE_SCALE = 0.85                  # 中文字号相对英文的缩放系数
MAX_FONT_SHRINK_RATIO = 0.6            # 最大字号缩小比例
```

### `.gitignore` 新增条目

```gitignore
# StreamTranslate 敏感配置
magic_mirror/config/.env
magic_mirror/config/llm_providers.yaml
```

---

## 数据流

```
[热键 Ctrl+Alt+T]
    │
    ▼
[RegionSelector]  ───→  QRect(x, y, w, h)         # 纯 UI
    │
    ▼
[TranslatePipeline.execute(bbox)]                   # 编排层 (只依赖协议)
    │
    ├─→ [IScreenCapture.capture()]  ───→ CaptureResult
    │
    ├─→ [IOcrEngine.recognize()]    ───→ List[TextBlock]
    │       (内部调用 preprocess)
    │
    ├─→ [ITranslator.translate()]   ───→ List[TranslatedBlock]
    │       (读取 llm_providers.yaml + .env)
    │
    └─→ [ILayoutEngine.compute()]   ───→ List[RenderBlock]
            (内部调用 color_sampler)
    │
    ▼
[MirrorOverlay.render(render_blocks)]               # 纯 UI
```

---

## 可扩展性矩阵 (开闭原则)

| 扩展场景 | 做法 | 需要修改的文件 |
|---------|------|--------------|
| 新增翻译后端 (如 Azure) | 新增 `translation/azure_translator.py` 实现 `ITranslator` | `provider_factory.py` 注册新类型 |
| 新增 OCR 引擎 (如 Tesseract) | 新增 `ocr/tesseract_engine.py` 实现 `IOcrEngine` | `main.py` 组装处切换 |
| 新增截图方式 | 新增 `capture/xxx_capture.py` 实现 `IScreenCapture` | `main.py` 组装处切换 |
| 更换翻译 Prompt | 修改 `translation/prompt_templates.py` | 仅此一个文件 |
| 新增语言对 (中→英) | 新增 Prompt 模板 + `settings.py` 增加方向配置 | `prompt_templates.py`, `settings.py` |
| 更换 LLM 后端地址 | 修改 `config/llm_providers.yaml` | 仅配置文件，零代码改动 |

---

## 实现阶段

### Phase 1: 基础管线 (MVP)

**目标**：跑通 框选 → 截图 → OCR → 翻译 → 覆盖 全流程。

| 步骤 | 任务 | 关键点 |
|------|------|--------|
| 1.1 | 搭建项目骨架 (目录结构 + `interfaces/` + `config/`) | SOLID 骨架先行，抽象层优先 |
| 1.2 | 定义数据模型 `interfaces/types.py` | 所有模块共享的 DTO |
| 1.3 | 定义四个核心协议 (`i_*.py`) | 契约先行，实现后补 |
| 1.4 | 实现 `capture/region_selector.py` | 全屏遮罩 + 鼠标拖拽框选 |
| 1.5 | 实现 `capture/pil_capture.py` | `IScreenCapture` 首个实现 |
| 1.6 | 实现 `ocr/rapid_ocr_engine.py` + `preprocess.py` | `IOcrEngine` 首个实现 |
| 1.7 | 实现 `translation/openai_translator.py` + `prompt_templates.py` + `provider_factory.py` | `ITranslator` 首个实现 |
| 1.8 | 实现 `layout/layout_engine.py` + `color_sampler.py` | `ILayoutEngine` 首个实现 |
| 1.9 | 实现 `ui/mirror_overlay.py` | 覆盖窗口渲染 |
| 1.10 | 实现 `pipeline.py` + `main.py` | 管线编排 + 组装 + 端到端冒烟测试 |

### Phase 2: 排版优化

| 步骤 | 任务 |
|------|------|
| 2.1 | 背景色精确采样（中值模糊 + 众数提取） |
| 2.2 | 文字颜色检测（从 OCR 区域提取前景色） |
| 2.3 | 字号自适应：中文字符宽度补偿 |
| 2.4 | 多行文本块处理（段落内换行） |
| 2.5 | 文本对齐方式检测（左/中/右对齐） |

### Phase 3: 体验增强

| 步骤 | 任务 |
|------|------|
| 3.1 | 翻译 streaming 渐进渲染 |
| 3.2 | 加载动画（翻译等待时显示骨架屏/脉冲效果） |
| 3.3 | 覆盖层右键菜单（复制文本、重新翻译、关闭） |
| 3.4 | 多次翻译管理（同时存在多个覆盖层） |
| 3.5 | 热键自定义 |
| 3.6 | 翻译缓存（相同文本不重复调用 API） |

### Phase 4: 高级功能（可选）

| 步骤 | 任务 |
|------|------|
| 4.1 | 支持中→英翻译方向 |
| 4.2 | 支持更多语言对 |
| 4.3 | 翻译历史记录 |
| 4.4 | 与 QuickDict 集成（热键不冲突、共享 OCR 引擎） |

---

## Prompt 工程

### 翻译 Prompt（核心）

定义在 `translation/prompt_templates.py`，与翻译后端实现完全解耦。

```text
System:
你是一个专业的英中翻译引擎，专门用于屏幕文本的实时翻译。

规则：
1. 将输入的英文文本翻译为简体中文
2. 输入是一组带编号的文本片段，来自屏幕截图的 OCR 识别
3. 保持编号一一对应，逐条翻译
4. 翻译要求自然、简洁，符合中文表达习惯
5. UI 元素（按钮、菜单）翻译要简短精炼
6. 专有名词保持英文原文（如 Python, GitHub, Windows）
7. 如果某条文本不是有意义的英文（如乱码、符号），原样返回
8. 严格以 JSON 数组格式输出：[{"id": 1, "zh": "..."}, {"id": 2, "zh": "..."}, ...]

User:
请翻译以下文本：
1. File
2. Edit
3. View
4. The quick brown fox jumps over the lazy dog.
5. Save changes before closing?
```

### 预期输出

```json
[
  {"id": 1, "zh": "文件"},
  {"id": 2, "zh": "编辑"},
  {"id": 3, "zh": "视图"},
  {"id": 4, "zh": "敏捷的棕色狐狸跳过了那只懒狗。"},
  {"id": 5, "zh": "关闭前是否保存更改？"}
]
```

---

## 风险与挑战

| 风险 | 影响 | 缓解策略 |
|------|------|---------|
| OCR 识别不准确 | 翻译质量下降 | 多预处理变体 + 置信度过滤 + Prompt 提示 AI 处理噪声文本 |
| 中文排版溢出 | 覆盖效果差 | 自适应字号 + 允许轻微扩展 + 长文本截断省略 |
| API 延迟高 | 用户等待久 | streaming 渐进显示 + 加载动画 + 翻译缓存 |
| 硬件加速窗口截图黑屏 | 无法识别 | dxcam fallback（已有方案） |
| DPI 缩放不一致 | 坐标偏移 | DPI-aware 坐标转换，物理/逻辑像素统一 |
| 背景色采样不准确 | 覆盖层视觉突兀 | 高斯模糊 + 边缘扩展采样区域 |
| LLM 后端迁移/变更 | 需要改代码 | Protocol 隔离 + YAML 配置外部化 → 零代码切换 |

---

## 依赖清单

```txt
# 已有（与 QuickDict 共享）
PyQt6
Pillow
rapidocr-onnxruntime
opencv-python-headless
numpy
pynput
dxcam

# 新增
openai          # OpenAI 兼容 API 客户端
python-dotenv   # .env 环境变量加载
pyyaml          # llm_providers.yaml 配置解析
```
