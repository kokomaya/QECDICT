# StreamTranslate — 开发任务清单

> 按 Phase 分阶段，每个 Task 为一个可独立完成和验证的最小工作单元。  
> 遵循 SOLID 原则：抽象层优先，接口先行，实现后补。  
> 复杂任务的实现细节见 `tasks/` 目录下的对应文件。

---

## Phase 1 — 基础管线 MVP

### Task 1: 项目骨架搭建
- **目标**：创建完整目录结构、配置框架、依赖文件
- **产出文件**：`stream_translate/` 整体目录骨架
- **步骤**：
  1. 创建目录结构：
     ```
     stream_translate/
     ├── __init__.py
     ├── main.py                 (空文件, 占位)
     ├── pipeline.py             (空文件, 占位)
     ├── config/
     │   ├── __init__.py
     │   ├── settings.py
     │   ├── llm_providers.example.yaml
     │   └── .env.example
     ├── interfaces/
     │   ├── __init__.py
     │   ├── types.py
     │   ├── i_screen_capture.py
     │   ├── i_ocr_engine.py
     │   ├── i_translator.py
     │   └── i_layout_engine.py
     ├── capture/
     │   ├── __init__.py
     │   ├── region_selector.py  (空文件, 占位)
     │   └── pil_capture.py      (空文件, 占位)
     ├── ocr/
     │   ├── __init__.py
     │   ├── rapid_ocr_engine.py (空文件, 占位)
     │   └── preprocess.py       (空文件, 占位)
     ├── translation/
     │   ├── __init__.py
     │   ├── openai_translator.py(空文件, 占位)
     │   ├── prompt_templates.py (空文件, 占位)
     │   └── provider_factory.py (空文件, 占位)
     ├── layout/
     │   ├── __init__.py
     │   ├── layout_engine.py    (空文件, 占位)
     │   └── color_sampler.py    (空文件, 占位)
     ├── ui/
     │   ├── __init__.py
     │   ├── mirror_overlay.py   (空文件, 占位)
     │   └── loading_indicator.py(空文件, 占位)
     └── requirements.txt
     ```
  2. 编写 `requirements.txt`：
     ```
     PyQt6
     Pillow
     rapidocr-onnxruntime
     opencv-python-headless
     numpy
     pynput
     dxcam
     openai
     python-dotenv
     pyyaml
     ```
  3. 在项目根目录 `.gitignore` 追加：
     ```
     stream_translate/config/.env
     stream_translate/config/llm_providers.yaml
     ```
  4. 在 `.venv` 中安装新增依赖：`pip install openai python-dotenv pyyaml`
- **验收**：目录结构完整；`import openai, dotenv, yaml` 不报错

---

### Task 2: 数据模型 & 抽象接口定义
- **目标**：定义所有共享数据类型和四个核心 Protocol 接口
- **产出文件**：`interfaces/types.py`, `i_screen_capture.py`, `i_ocr_engine.py`, `i_translator.py`, `i_layout_engine.py`
- **步骤**：
  1. 实现 `interfaces/types.py` — 四个 `@dataclass`：
     - `TextBlock`: text, bbox (四角坐标), font_size_est, confidence
     - `TranslatedBlock`: source (TextBlock), translated_text
     - `RenderBlock`: screen_x, screen_y, width, height, translated_text, font_size, bg_color (RGBA tuple), text_color (RGB tuple)
     - `CaptureResult`: image (np.ndarray), screen_bbox (x, y, w, h)
  2. 实现 `interfaces/i_screen_capture.py` — `IScreenCapture(Protocol)`：
     - `capture(bbox: Tuple[int,int,int,int]) -> CaptureResult`
  3. 实现 `interfaces/i_ocr_engine.py` — `IOcrEngine(Protocol)`：
     - `recognize(image: np.ndarray) -> List[TextBlock]`
  4. 实现 `interfaces/i_translator.py` — `ITranslator(Protocol)`：
     - `translate(blocks: List[TextBlock]) -> List[TranslatedBlock]`
  5. 实现 `interfaces/i_layout_engine.py` — `ILayoutEngine(Protocol)`：
     - `compute_layout(blocks: List[TranslatedBlock], screenshot: np.ndarray, screen_bbox: Tuple) -> List[RenderBlock]`
  6. 在 `interfaces/__init__.py` 中统一导出所有类型和协议
- **验收**：`from stream_translate.interfaces import TextBlock, ITranslator` 等导入无报错；`mypy` 或 `pyright` 类型检查通过

---

### Task 3: 配置层实现
- **目标**：实现通用配置 + LLM 后端配置加载 + 凭证管理，确保敏感信息完全隔离
- **产出文件**：`config/settings.py`, `config/llm_providers.example.yaml`, `config/.env.example`, `config/__init__.py`
- **步骤**：
  1. 实现 `config/settings.py` — 通用配置常量：
     ```python
     HOTKEY_TRIGGER = "ctrl+alt+t"
     OCR_CONFIDENCE_THRESHOLD = 0.5
     OCR_DET_BOX_THRESH = 0.3
     OVERLAY_OPACITY = 255
     SELECTOR_MASK_COLOR = (0, 0, 0, 80)
     SELECTOR_BORDER_COLOR = (0, 120, 215)
     FONT_FAMILY_ZH = "Microsoft YaHei"
     FONT_SIZE_SCALE = 0.85
     MAX_FONT_SHRINK_RATIO = 0.6
     ```
  2. 编写 `config/llm_providers.example.yaml` — 脱敏示例：
     ```yaml
     default_provider: "my_provider"
     providers:
       my_provider:
         type: "openai_compatible"
         base_url: "https://your-api-endpoint:port"
         model: "your-model-name"
         headers:
           useLegacyCompletionsEndpoint: "false"
           X-Tenant-ID: "default_tenant"
         timeout: 60
         max_retries: 2
         stream: false
     ```
  3. 编写 `config/.env.example`：
     ```env
     API_TOKEN=your_api_token_here
     API_USERNAME=your_username_here
     ```
  4. 实现 `config/__init__.py` — 配置加载器：
     - `load_llm_config() -> dict`: 加载 `llm_providers.yaml`，不存在时抛出明确错误提示用户复制 example
     - `load_env()`: 调用 `dotenv.load_dotenv()` 加载 `.env`
     - `get_default_provider() -> dict`: 返回默认 provider 的完整配置
  5. **确认**：代码中不出现任何硬编码 URL / IP / 模型名
- **验收**：复制 example 文件为实际配置并填入值后，`load_llm_config()` 正确返回配置字典；缺少配置文件时给出友好错误信息

---

### Task 4: 区域框选 — `capture/region_selector.py`
- **目标**：全屏半透明遮罩 + 鼠标拖拽矩形框选，纯 UI 组件
- **产出文件**：`capture/region_selector.py`
- **步骤**：
  1. 创建 `RegionSelector(QWidget)` 类：
     - Window flags: `FramelessWindowHint | WindowStaysOnTopHint | Tool`
     - `WA_TranslucentBackground` 属性
     - 全屏覆盖所有显示器（合并虚拟桌面几何 `QApplication.primaryScreen().virtualGeometry()`）
  2. 实现鼠标事件：
     - `mousePressEvent`: 记录起点坐标
     - `mouseMoveEvent`: 实时更新终点，触发 `update()` 重绘
     - `mouseReleaseEvent`: 计算最终矩形，发射 `sig_region_selected(QRect)` 信号，关闭自身
  3. 实现 `paintEvent`：
     - 整屏半透明黑色遮罩 (`SELECTOR_MASK_COLOR` from settings)
     - 框选区域透明镂空（用 QPainterPath 差集）
     - 框选边框：2px 实线 (`SELECTOR_BORDER_COLOR` from settings)
  4. `keyPressEvent`: Esc 键取消框选，发射 `sig_cancelled()` 信号
  5. 提供 `start()` 方法：显示全屏并进入框选状态
- **验收**：独立运行，按下鼠标拖拽出矩形区域后打印 `QRect` 坐标；Esc 取消；多显示器下遮罩覆盖所有屏幕

---

### Task 5: 屏幕截图 — `capture/pil_capture.py`
- **目标**：实现 `IScreenCapture` 协议，截取指定屏幕区域
- **产出文件**：`capture/pil_capture.py`
- **步骤**：
  1. 创建 `PilScreenCapture` 类，实现 `IScreenCapture` 协议
  2. `capture(bbox)` 方法：
     - 将 `(x, y, w, h)` 转换为 PIL 格式 `(left, top, right, bottom)`
     - 调用 `PIL.ImageGrab.grab(bbox=..., all_screens=True)`
     - 检测黑屏（全零像素比例 > 95%），如果黑屏尝试 dxcam fallback
     - 将 PIL Image 转换为 `np.ndarray` (BGR 格式)
  3. dxcam fallback 逻辑（参考 QuickDict `_ocr_capture.py`）：
     - 使用 `ctypes.windll.user32.EnumDisplayMonitors` 确定目标显示器
     - 用 `dxcam.create(output_idx=...)` 截取
  4. DPI 处理：获取系统 DPI 缩放比例，确保逻辑坐标 → 物理像素正确映射
  5. 返回 `CaptureResult(image=ndarray, screen_bbox=bbox)`
- **验收**：对屏幕任意区域截图，保存为 PNG 确认图像内容正确；在硬件加速窗口（如 Teams）上测试 fallback

---

### Task 6: OCR 预处理 — `ocr/preprocess.py`
- **目标**：图像预处理变体生成器，独立于 OCR 引擎
- **产出文件**：`ocr/preprocess.py`
- **步骤**：
  1. 实现 `generate_variants(image: np.ndarray) -> List[np.ndarray]` 函数
  2. 8 种预处理变体（参考 QuickDict `_ocr_preprocess.py`）：
     - ① 原图 BGR
     - ② CLAHE 对比度增强
     - ③ Otsu 二值化
     - ④ 自适应阈值
     - ⑤ 形态学处理（去下划线）
     - ⑥ 2x 双三次放大
     - ⑦ 2x 放大 + 锐化
     - ⑧ 2x 放大 + CLAHE
  3. 所有变体函数为纯函数，输入输出均为 `np.ndarray`
  4. 不依赖任何 OCR 库，仅使用 `cv2` 和 `numpy`
- **验收**：输入一张截图，生成 8 张变体图像，保存查看效果合理

---

### Task 7: OCR 识别引擎 — `ocr/rapid_ocr_engine.py`
- **目标**：实现 `IOcrEngine` 协议，从图像提取带坐标的文本块
- **产出文件**：`ocr/rapid_ocr_engine.py`
- **步骤**：
  1. 创建 `RapidOcrEngine` 类，实现 `IOcrEngine` 协议
  2. 构造函数：惰性加载 RapidOCR 实例（首次调用 `recognize` 时初始化）
     ```python
     from rapidocr_onnxruntime import RapidOCR
     self._ocr = RapidOCR(det_box_thresh=OCR_DET_BOX_THRESH)
     ```
  3. `recognize(image)` 方法：
     - 调用 `self._ocr(image)` 获取结果列表 `[(bbox_points, text, confidence), ...]`
     - 过滤 `confidence < OCR_CONFIDENCE_THRESHOLD` 的结果
     - 对每个结果构建 `TextBlock`：
       - `bbox`: 直接使用四角坐标
       - `font_size_est`: `(bbox[3][1] - bbox[0][1])` 即 bbox 高度
       - 去除文本首尾空白
     - 可选：对预处理变体逐一识别，合并/去重结果
  4. 处理 OCR 返回 `None` 或空结果的情况
- **验收**：对含英文文本的截图执行 `recognize()`，返回正确的文本块列表，包含文本、坐标、字号估算

---

### Task 8: Prompt 模板 — `translation/prompt_templates.py`
- **目标**：集中管理翻译 Prompt，与后端实现解耦
- **产出文件**：`translation/prompt_templates.py`
- **步骤**：
  1. 定义 `SYSTEM_PROMPT` 常量：
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
     ```
  2. 实现 `build_user_prompt(texts: list[tuple[int, str]]) -> str`：
     - 输入 `[(1, "File"), (2, "Edit"), ...]`
     - 输出格式化的编号文本列表
  3. 实现 `parse_translation_response(response_text: str) -> dict[int, str]`：
     - 解析 AI 返回的 JSON 数组
     - 返回 `{id: translated_text}` 映射
     - 处理 JSON 解析失败的情况（AI 可能返回非标准 JSON）：尝试从响应文本中提取 JSON 片段
- **验收**：`build_user_prompt` 输出格式正确；`parse_translation_response` 能正确解析标准和非标准 JSON 响应

---

### Task 9: 翻译后端工厂 — `translation/provider_factory.py`
- **目标**：根据 YAML 配置创建 `ITranslator` 实例，调用方无需关心后端类型
- **产出文件**：`translation/provider_factory.py`
- **步骤**：
  1. 实现 `create_translator(provider_config: dict) -> ITranslator`：
     - 根据 `provider_config["type"]` 分发：
       - `"openai_compatible"` → 创建 `OpenAITranslator` 实例
       - 未知类型 → 抛出 `ValueError` 并列出支持的类型
     - 将配置参数（base_url, model, headers, timeout 等）传入构造函数
  2. 实现 `create_translator_from_config() -> ITranslator`（便捷方法）：
     - 内部调用 `config.load_llm_config()` + `config.get_default_provider()`
     - 从 `os.environ` 获取 `API_TOKEN`
     - 组装完整配置后调用 `create_translator()`
- **验收**：填入有效配置后，`create_translator_from_config()` 返回可用的 translator 实例

---

### Task 10: OpenAI 兼容翻译实现 — `translation/openai_translator.py`
- **目标**：实现 `ITranslator` 协议，调用 OpenAI 兼容 API 批量翻译
- **产出文件**：`translation/openai_translator.py`
- **步骤**：
  1. 创建 `OpenAITranslator` 类，实现 `ITranslator` 协议
  2. 构造函数接收配置参数（全部来自外部，不硬编码）：
     ```python
     def __init__(self, api_key: str, base_url: str, model: str,
                  headers: dict = None, timeout: int = 60, stream: bool = False):
         self._client = openai.OpenAI(
             api_key=api_key,
             base_url=base_url,
             default_headers=headers or {},
         )
         self._model = model
         self._timeout = timeout
         self._stream = stream
     ```
  3. `translate(blocks)` 方法：
     - 空列表直接返回 `[]`
     - 构建编号文本列表：`[(i+1, block.text) for i, block in enumerate(blocks)]`
     - 调用 `prompt_templates.build_user_prompt()` 生成 user prompt
     - 调用 `self._client.chat.completions.create()` 发送请求
     - 调用 `prompt_templates.parse_translation_response()` 解析响应
     - 按编号匹配，构建 `TranslatedBlock` 列表
     - 未匹配到翻译的文本块：`translated_text` 回退为原文
  4. 错误处理：
     - API 超时 / 网络错误 → 日志记录 + 所有块回退为原文
     - JSON 解析失败 → 日志记录 + 回退
- **验收**：传入 `[TextBlock("Hello", ...), TextBlock("World", ...)]`，返回正确的 `TranslatedBlock` 列表；API 不可用时优雅降级

---

### Task 11: 颜色采样 — `layout/color_sampler.py`
- **目标**：从截图中提取文本块的背景色和前景色
- **产出文件**：`layout/color_sampler.py`
- **步骤**：
  1. 实现 `sample_background_color(image: np.ndarray, bbox: List[List[float]]) -> Tuple[int,int,int,int]`：
     - 在 bbox 外围扩展 3-5px 取样区域
     - 对取样区域做中值模糊
     - 取众数（出现最多的颜色）作为背景色
     - 返回 RGBA（A 固定为 255）
  2. 实现 `sample_text_color(image: np.ndarray, bbox: List[List[float]], bg_color: Tuple) -> Tuple[int,int,int]`：
     - 在 bbox 内部区域提取前景色
     - 策略：K-Means 聚类取与背景色差异最大的簇中心
     - 简化策略：直接用 `(255-bg_r, 255-bg_g, 255-bg_b)` 反色
     - MVP 阶段用简化策略即可
  3. 处理边界情况：bbox 超出图像范围时 clip
- **验收**：对白底黑字截图，返回背景 `(255,255,255,255)` + 前景 `(0,0,0)`；对深色背景截图同样合理

---

### Task 12: 排版引擎 — `layout/layout_engine.py`
- **目标**：实现 `ILayoutEngine` 协议，将翻译结果映射为可渲染块
- **产出文件**：`layout/layout_engine.py`
- **步骤**：
  1. 创建 `DefaultLayoutEngine` 类，实现 `ILayoutEngine` 协议
  2. `compute_layout(blocks, screenshot, screen_bbox)` 方法：
     - 遍历每个 `TranslatedBlock`：
     - **坐标映射**：OCR bbox (相对截图) → 屏幕绝对坐标
       - `screen_x = screen_bbox[0] + bbox_left`
       - `screen_y = screen_bbox[1] + bbox_top`
     - **字号计算**：
       - 基础字号 = `source.font_size_est * FONT_SIZE_SCALE`
       - 用 `QFontMetrics` 测量中文文本渲染宽度
       - 如果溢出 bbox 宽度：按比例缩小字号，但不低于 `font_size * MAX_FONT_SHRINK_RATIO`
       - 如果仍溢出：允许宽度扩展最多 30%
     - **颜色采样**：调用 `color_sampler` 获取 bg_color + text_color
     - 构建 `RenderBlock` 并添加到结果列表
  3. 处理空 blocks 列表
- **验收**：传入模拟的 `TranslatedBlock` + 截图，返回合理的 `RenderBlock` 列表（坐标、字号、颜色均有值）

---

### Task 13: 魔法镜子覆盖窗口 — `ui/mirror_overlay.py`
- **目标**：在屏幕上渲染翻译后的中文覆盖层，纯 UI 组件
- **产出文件**：`ui/mirror_overlay.py`
- **步骤**：
  1. 创建 `MirrorOverlay(QWidget)` 类：
     - Window flags: `FramelessWindowHint | WindowStaysOnTopHint | Tool`
     - `WA_TranslucentBackground` 属性
  2. 实现 `render(render_blocks: List[RenderBlock], screen_bbox: Tuple)` 方法：
     - 设置窗口位置和大小为 `screen_bbox` 对应的屏幕区域
     - 存储 `render_blocks` 供 `paintEvent` 使用
     - 调用 `show()` 显示窗口
  3. 实现 `paintEvent`：
     - 使用 `QPainter` 遍历 render_blocks：
       - 坐标转换：screen 绝对坐标 → 窗口局部坐标（减去窗口左上角）
       - 绘制背景色矩形（`fillRect`，使用 `bg_color`）
       - 设置字体（`FONT_FAMILY_ZH`，`font_size`）
       - 设置文字颜色（`text_color`）
       - `drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, translated_text)`
  4. 交互：
     - `keyPressEvent`: Esc 关闭并隐藏
     - 默认设置 `WA_TransparentForMouseEvents`，鼠标事件穿透
     - 提供 `close_overlay()` 方法供外部调用
  5. 提供 `clear()` 方法：隐藏窗口、清空 render_blocks
- **验收**：手动构建测试 `RenderBlock` 列表，调用 `render()` 后屏幕上正确显示中文文字覆盖；Esc 可关闭

---

### Task 14: 加载动画 — `ui/loading_indicator.py`
- **目标**：翻译等待时在选定区域显示加载指示
- **产出文件**：`ui/loading_indicator.py`
- **步骤**：
  1. 创建 `LoadingIndicator(QWidget)` 类：
     - 无边框、置顶、半透明背景
  2. 实现 `show_at(screen_bbox: Tuple)` 方法：
     - 在选定区域中心显示加载动画
     - 动画：旋转圆弧 + "翻译中..." 文字（`QTimer` 驱动旋转角度）
  3. 实现 `dismiss()` 方法：淡出并隐藏
- **验收**：调用 `show_at()` 后屏幕上出现加载动画；`dismiss()` 后消失

---

### Task 15: 管线编排 — `pipeline.py`
- **目标**：串联所有组件的管线，只依赖抽象协议
- **产出文件**：`pipeline.py`
- **步骤**：
  1. 创建 `TranslatePipeline` 类：
     ```python
     def __init__(self, capture: IScreenCapture, ocr: IOcrEngine,
                  translator: ITranslator, layout: ILayoutEngine):
     ```
  2. 实现 `execute(bbox: Tuple[int,int,int,int]) -> Tuple[List[RenderBlock], Tuple]`：
     - 步骤 1: `capture.capture(bbox)` → `CaptureResult`
     - 步骤 2: `ocr.recognize(result.image)` → `List[TextBlock]`
     - 步骤 3: `translator.translate(blocks)` → `List[TranslatedBlock]`
     - 步骤 4: `layout.compute_layout(translated, result.image, result.screen_bbox)` → `List[RenderBlock]`
     - 返回 `(render_blocks, screen_bbox)`
  3. 每步之间可加日志输出（调试用）
  4. 错误处理：任一步骤失败时记录日志并抛出，由调用方处理
  5. **确认**：文件中不 import 任何 `capture/`, `ocr/`, `translation/`, `layout/` 包的具体类
- **验收**：用 mock 对象注入四个协议实现，调用 `execute()` 按顺序执行；类型检查通过

---

### Task 16: 主程序集成 — `main.py`
- **目标**：组装所有组件，串联 UI 交互与管线，实现端到端流程
- **产出文件**：`main.py`
- **步骤**：
  1. 实现 `create_pipeline(config) -> TranslatePipeline`（Composition Root）：
     ```python
     capture = PilScreenCapture()
     ocr = RapidOcrEngine()
     translator = create_translator_from_config()
     layout = DefaultLayoutEngine()
     return TranslatePipeline(capture, ocr, translator, layout)
     ```
     **注意**：这是整个项目中唯一 import 具体实现类的地方
  2. 创建 `StreamTranslateApp(QObject)` 控制器：
     - 持有 `RegionSelector`, `MirrorOverlay`, `LoadingIndicator`, `TranslatePipeline`
     - 注册全局热键 (`pynput.keyboard.Listener`)：`Ctrl+Alt+T` 触发框选
  3. 信号流连接：
     - 热键触发 → `RegionSelector.start()`
     - `RegionSelector.sig_region_selected(QRect)` → `_on_region_selected(rect)`
     - `_on_region_selected`:
       1. 显示 `LoadingIndicator`
       2. 在 `QThread` / `QRunnable` 中执行 `pipeline.execute(bbox)`
       3. 完成后在主线程：隐藏 loading → `MirrorOverlay.render(blocks, bbox)`
     - `RegionSelector.sig_cancelled()` → 什么都不做
  4. 系统托盘（可选，MVP 阶段简化）：
     - `QSystemTrayIcon` + 右键菜单：翻译区域 / 退出
  5. 入口 `main()` 函数：
     - 设置 DPI 感知
     - 创建 `QApplication`
     - 加载配置 (`config.load_env()`, `config.load_llm_config()`)
     - 创建 `StreamTranslateApp`
     - `app.exec()`
  6. `if __name__ == "__main__": main()`
- **验收**：运行 `python -m stream_translate.main`，按 `Ctrl+Alt+T`，拖拽框选英文区域，等待后该区域英文被中文覆盖替换，Esc 关闭覆盖层

---

## Phase 2 — 排版优化

### Task 17: 背景色精确采样
- **目标**：提升颜色采样精度，减少覆盖层视觉突兀感
- **修改文件**：`layout/color_sampler.py`
- **步骤**：
  1. 改进 `sample_background_color`：中值模糊 + 直方图众数提取替代简单均值
  2. 扩展采样区域：bbox 外围 5-10px，排除文字像素干扰
  3. 对深色 / 浅色 / 渐变背景分别验证

### Task 18: 前景色检测
- **目标**：准确提取文字颜色而非简单反色
- **修改文件**：`layout/color_sampler.py`
- **步骤**：
  1. 改进 `sample_text_color`：K-Means (k=2) 聚类，选择与背景差异最大的簇
  2. 处理彩色文字（如链接蓝色、错误红色）

### Task 19: 中文字号自适应
- **目标**：精确计算中文渲染字号，避免溢出或过小
- **修改文件**：`layout/layout_engine.py`
- **步骤**：
  1. 使用 `QFontMetrics.horizontalAdvance()` 精确测量文本宽度
  2. 二分查找最优字号：在 `[font_size * MAX_SHRINK, font_size]` 区间内找最大不溢出的字号
  3. 处理中英混排文本（部分保持英文原文的情况）

### Task 20: 多行文本块处理
- **目标**：支持段落级文本的换行渲染
- **修改文件**：`layout/layout_engine.py`, `ui/mirror_overlay.py`
- **步骤**：
  1. 检测 OCR 结果中相邻且 Y 坐标接近的文本块，合并为段落
  2. 在 `RenderBlock` 中支持多行文本
  3. `MirrorOverlay` 的 `drawText` 改用 `QTextDocument` 或手动换行渲染

### Task 21: 文本对齐检测
- **目标**：检测原文的对齐方式并在翻译中保持
- **修改文件**：`layout/layout_engine.py`
- **步骤**：
  1. 分析同一列的多个文本块的 X 坐标分布
  2. 判断左对齐 / 居中 / 右对齐
  3. 在 `RenderBlock` 中增加 `alignment` 字段
  4. `MirrorOverlay` 根据 alignment 调整 `drawText` 的 flag

---

## Phase 3 — 体验增强

### Task 22: 翻译 Streaming 渐进渲染
- **目标**：翻译结果逐条显示，减少等待感
- **修改文件**：`translation/openai_translator.py`, `pipeline.py`, `ui/mirror_overlay.py`
- **步骤**：
  1. `OpenAITranslator` 增加 streaming 翻译方法，逐个解析出翻译结果
  2. `pipeline.py` 增加回调接口：每翻译完一条即通知 UI
  3. `MirrorOverlay` 支持增量渲染：逐块添加 RenderBlock 并 `update()`

### Task 23: 加载骨架屏
- **目标**：OCR 完成后、翻译完成前，显示占位骨架
- **修改文件**：`ui/mirror_overlay.py`
- **步骤**：
  1. OCR 完成后先渲染灰色占位条（与 bbox 等大）
  2. 翻译完成后逐条替换为真实文字
  3. 替换时使用淡入动画

### Task 24: 覆盖层右键菜单
- **目标**：右键菜单支持复制文本、重新翻译、关闭
- **修改文件**：`ui/mirror_overlay.py`
- **步骤**：
  1. 取消 `WA_TransparentForMouseEvents`，改为捕获右键事件
  2. 实现 `contextMenuEvent`：复制所有翻译文本 / 复制选中区域 / 重新翻译 / 关闭
  3. 左键点击仍穿透（用 `hitTest` 区分）

### Task 25: 多覆盖层管理
- **目标**：支持同时存在多个翻译覆盖层
- **修改文件**：`main.py`
- **步骤**：
  1. `StreamTranslateApp` 维护 `List[MirrorOverlay]`
  2. 每次框选创建新的 overlay
  3. 全局 Esc 关闭最近一个 overlay；`Ctrl+Shift+Esc` 关闭全部

### Task 26: 热键自定义
- **目标**：允许用户自定义触发热键
- **修改文件**：`config/settings.py`, `main.py`
- **步骤**：
  1. `settings.py` 中 `HOTKEY_TRIGGER` 支持字符串解析
  2. 实现热键字符串到 pynput Key 对象的映射
  3. 可选：设置对话框修改热键

### Task 27: 翻译缓存
- **目标**：相同文本不重复调用 API
- **修改文件**：`translation/openai_translator.py`
- **步骤**：
  1. 在 `OpenAITranslator` 中增加 LRU 缓存（基于文本 hash）
  2. 缓存命中时直接返回，跳过 API 调用
  3. 缓存容量可配置（`settings.py` 中 `TRANSLATION_CACHE_SIZE`）

---

## Phase 4 — 高级功能（可选）

### Task 28: 双向翻译
- **目标**：支持中→英翻译方向
- **修改文件**：`translation/prompt_templates.py`, `config/settings.py`
- **步骤**：
  1. 新增 `SYSTEM_PROMPT_ZH_TO_EN` 模板
  2. `settings.py` 增加 `TRANSLATION_DIRECTION` 配置项
  3. 托盘菜单增加方向切换

### Task 29: 多语言支持
- **目标**：扩展到更多语言对
- **修改文件**：`translation/prompt_templates.py`, `config/settings.py`
- **步骤**：
  1. Prompt 模板参数化：`{source_lang}` → `{target_lang}`
  2. 配置文件增加语言对选项
  3. 系统托盘增加语言选择菜单

### Task 30: 翻译历史记录
- **目标**：保存每次翻译的原文和译文
- **新增文件**：`stream_translate/history.py`
- **步骤**：
  1. SQLite 存储：时间戳 + 原文列表 + 译文列表 + 截图缩略图(可选)
  2. 托盘菜单增加"历史记录"入口
  3. 简易列表 UI 展示历史

### Task 31: QuickDict 集成
- **目标**：与 QuickDict 主项目合并，共享基础设施
- **步骤**：
  1. 将 `stream_translate` 作为 QuickDict 的子功能
  2. 共享 OCR 引擎实例（避免重复加载模型）
  3. 热键不冲突：QuickDict `Ctrl×2` vs StreamTranslate `Ctrl+Alt+T`
  4. 共享系统托盘图标
