# Magic Mirror — OCR 识别准确性提升方案调研

> 调研目标：梳理开源项目与商业产品中提升 OCR 识别准确性的策略，结合 Magic Mirror 当前架构，给出可落地的改进方案。

---

## 一、设计原则回顾

| 场景 | 优先级 | 说明 |
|------|--------|------|
| 纯文字 | **提取准确 > 位置精度** | 文字必须 100% 提取到，翻译必须准确，位置可以略有偏移 |
| 图文混排 | **位置准确 + 不漏识别** | 位置尽量贴合原文，不遗漏任何文本区域 |

---

## 二、竞品 & 开源项目调研

### 2.1 RapidOCR / PaddleOCR（我们当前使用的引擎）

**架构**：DB 文本检测 → 方向分类 → CRNN 文本识别（PP-OCR 三阶段 pipeline）

**关键参数**（来自 RapidOCR 官方文档）：

| 参数 | 默认值 | 作用 | 调优方向 |
|------|--------|------|---------|
| `text_score` | 0.5 | 最终文本置信度过滤 | **降低到 0.3~0.4 可减少漏检** |
| `box_thresh` | 0.5 | 检测框保留阈值 | **降低到 0.3 提高召回率** |
| `thresh` | 0.3 | 前景/背景分割阈值 | 保持 0.3 |
| `unclip_ratio` | 1.6 | 检测框扩展比例 | **增大到 1.8~2.0 可包含更多边缘文字** |
| `use_dilation` | true | 膨胀处理 | 保持开启 |
| `limit_side_len` | 736 | 输入图像最小边 | **增大到 960 可提升小文字检测** |
| `min_height` | 30 | 跳过检测的最小高度 | 对单行文本直接识别 |

**RapidOCR FAQ 关键发现**：
- 边缘文字无法识别 → 增加 padding（我们已做，从 12 增到 16）
- GPU 模式下动态 shape 导致比 CPU 慢 → 建议 CPU 用 onnxruntime，GPU 用 paddle
- **PP-OCRv5 已发布**，检测和识别模型都有显著提升

**可行动项**：
1. ★★★ 升级到 PP-OCRv5 模型（检测 + 识别均有改进）
2. ★★★ 降低 `box_thresh` 到 0.3（当前我们通过 `det_box_thresh` 已部分做到）
3. ★★ 增大 `unclip_ratio`（扩大检测框，减少截断文字）
4. ★★ 增大 `limit_side_len` 到 960（提升小文字检测能力）

---

### 2.2 Umi-OCR（43.4k stars）

**架构**：PaddleOCR-json / RapidOCR-json 引擎 + QML 界面

**识别策略特点**：
- **排版解析**：多种后处理方案（多栏-按自然段换行 / 单栏-保留缩进 / 不做处理）
- **忽略区域**：用户可绘制矩形排除水印/Logo 区域，减少干扰
- **文本块级过滤**：不是按字符而是按整个文本块做忽略判断
- 支持 OCR 插件系统，可切换不同识别引擎

**对 Magic Mirror 的启发**：
1. ★★ 实现"忽略区域"机制 → 减少非文字区域的干扰误识别
2. ★ 排版后处理可参考其多栏解析逻辑

---

### 2.3 manga-image-translator（9.8k stars）

**架构**：文本检测(CTD/CRAFT) → OCR(Manga OCR/48px) → 翻译(多引擎) → 图像修复(LaMa) → 文字渲染

**提升识别准确性的关键策略**（官方 Tips to Improve Translation Quality）：

| 策略 | 说明 | 适用性 |
|------|------|--------|
| **upscale_ratio** | 低分辨率图像先放大再检测，可显著提升小文字识别 | ★★★ 我们已有类似机制 |
| **detection_size** | 图像分辨率低时降低 detection_size，否则可能漏句 | ★★★ 非常关键 |
| **box_threshold** | 提高可过滤 OCR 乱码误检；降低可减少漏检 | ★★ 需要平衡 |
| **det_rotate** | 旋转图像再检测，可检出旋转文字 | ★ 场景少 |
| **det_invert** | 反色后检测，适合亮字暗底 | ★★ 屏幕截图常见 |
| **det_gamma_correct** | 伽马校正后检测，提升低对比度场景 | ★★ |
| **pre-dict / post-dict** | 翻译前后的文本替换字典，修正常见 OCR 错误 | ★★★ |
| **bounding box merging** | Manga OCR 的 bbox 合并策略 | ★★ |
| **font_color 覆盖** | 若 OCR 颜色检测不准，可强制指定 | ★ |

**关键设计思路**：
- **检测器选择**：CTD (Comic Text Detector) 对漫画效果好，default 对一般图像更好
- **OCR 选择**：48px 模型对日文最好（针对特定语言优化模型）
- **多阶段管线**：检测 → OCR → 翻译 → 修复 → 渲染，每阶段独立可调
- 文本颜色提取用 DPGMM（Dirichlet Process Gaussian Mixture Model），但作者表示效果不理想

**对 Magic Mirror 的启发**：
1. ★★★ **反色预处理变体**（`det_invert`）→ 亮色文字暗色背景场景极为关键
2. ★★★ **OCR 错误字典**（pre-dict）→ 建立常见 OCR 错误映射表，翻译前自动纠正
3. ★★ **伽马校正变体**（`det_gamma_correct`）→ 已有 CLAHE，但伽马校正是补充
4. ★★ **动态调整 detection_size**：根据截图分辨率自动选择合适的检测尺寸

---

### 2.4 pot-desktop（17.7k stars）

**架构**：Tauri 框架 + 多 OCR 引擎插件

**OCR 引擎策略**：
- **多引擎并行/备选**：系统 OCR、Tesseract.js（离线）、百度/腾讯/火山 API、RapidOCR、PaddleOCR
- **离线引擎组合**：Windows.Media.OCR（系统级）+ Tesseract.js + RapidOCR 插件
- **截图 OCR + 截图翻译**：区分纯 OCR 提取和 OCR+翻译两种模式

**对 Magic Mirror 的启发**：
1. ★ 多引擎备选/对比（复杂度高，短期不实际）
2. ★★ Windows.Media.OCR 作为备选引擎（系统内置，无需额外模型）

---

### 2.5 商业产品参考

| 产品 | 策略 | 可借鉴点 |
|------|------|---------|
| **Google Lens** | 多模型级联、超分辨率预处理、语言自适应 | 先检测文字区域再局部超分辨率 |
| **DeepL 截图翻译** | 系统级截图 + 云端 OCR + 神经机器翻译 | 云端引擎准确率极高 |
| **有道词典截图** | 本地 OCR + 云端纠错 + 上下文理解 | 本地快速识别 + 云端精确纠错 |
| **微信截图翻译** | 端侧模型 + 动态裁剪 + 自适应预处理 | 多尺度检测策略 |

---

## 三、当前 Magic Mirror OCR 管线分析

```
截图 → 预处理变体生成 → 多阈值检测 → 空间去重 → 字体分析 → CC 补漏 → 段落合并 → 翻译
          ↓                    ↓              ↓
    [原图/CLAHE/锐化/      [主阈值 0.3     [IoU/包含/
     放大/二值化/填充]       低阈值 0.1]     同行碎片]
```

### 当前已有的策略（已实现）
- ✅ 多变体预处理（6 种变体）
- ✅ 双阈值检测（主 0.3 + 低 0.1）
- ✅ 空间去重（IoU + 包含 + 交集面积 + 同行碎片）
- ✅ Connected Component 补漏
- ✅ 边界填充（16px）
- ✅ 低分辨率放大（2x/3x）

### 现有管线的薄弱环节

| 问题 | 分析 | 影响 |
|------|------|------|
| **① 缺少反色变体** | 亮色文字暗色背景（如终端/IDE 暗色主题）检测率低 | 漏识别 |
| **② 缺少伽马校正变体** | 低对比度但标准差>65 的场景无额外增强 | 漏识别 |
| **③ 去重时丢弃同行碎片** | `_significant_overlap` 判定为重复后直接丢弃，可能丢掉有效文字 | 文字丢失 |
| **④ 无 OCR 纠错机制** | OCR 常见错误（如 `l`→`1`, `O`→`0`, `rn`→`m`）直接进入翻译 | 翻译错误 |
| **⑤ 翻译 prompt 缺少纠错指引** | 未指导 LLM 自动纠正 OCR 噪声 | 翻译错误 |
| **⑥ 模型版本未升级** | 仍使用 PP-OCRv4，v5 已发布并有显著改进 | 整体准确率 |
| **⑦ limit_side_len 偏小** | 默认 736，对高分辨率屏幕截图可能不够 | 小文字漏检 |
| **⑧ unclip_ratio 偏保守** | 默认 1.6，检测框可能截断部分文字 | 文字截断 |

---

## 四、改进方案（按优先级排序）

### P0 — 投入小、见效快

#### 4.1 ★★★ 增加反色预处理变体

**原理**：暗色主题（IDE、终端、深色网页）中，文字为浅色、背景为深色。DB 检测器的前景分割假设文字为深色，对这类场景检测率低。反色后可以极大提升检出率。

**实现**：`preprocess.py` 增加反色变体

```python
def _invert(image: np.ndarray) -> np.ndarray | None:
    """反色：适用于亮字暗底场景（IDE、终端等暗色主题）。"""
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean_val = gray.mean()
        if mean_val < 127:  # 仅在整体偏暗时生成
            return cv2.bitwise_not(image)
        return None
    except Exception:
        return None
```

**触发条件**：仅当图像平均亮度 < 127 时生成，避免对亮色场景产生冗余变体。

---

#### 4.2 ★★★ OCR 纠错字典（pre-translation fix）

**原理**：OCR 有固定的常见错误模式，在翻译前修正可以显著提升翻译准确性。manga-image-translator 已证明 pre-dict 的有效性。

**实现**：新建 `magic_mirror/ocr/text_corrector.py`

```python
# 常见 OCR 错误映射（英文场景）
COMMON_OCR_FIXES = {
    " l ": " I ",        # 小写 l 误识为 I
    "0f": "of",          # 数字 0 误识为字母 O
    "tbe": "the",        # 常见连笔误识
    "witb": "with",
    "wbich": "which",
    "tbat": "that",
    " ll ": " II ",      # 罗马数字
    "rn": "m",           # 像素级相似（需要上下文判断）
    "Iine": "line",
    "Iist": "list",
    "Ioad": "load",
}
```

**注意**：rn→m 等替换需要结合上下文（如词典验证），避免误纠。

---

#### 4.3 ★★★ 增强翻译 Prompt 的纠错能力

**原理**：即使不做显式纠错，LLM 本身具有从上下文推断和纠正 OCR 错误的能力。在 prompt 中明确指引可以激活这个能力。

**实现**：在翻译 system prompt 中增加规则

```
- OCR 识别可能存在个别字符错误（如 l/1/I 混淆、rn/m 混淆），翻译时请根据上下文自动纠正，确保翻译通顺
```

---

#### 4.4 ★★ 去重时合并同行碎片而非丢弃

**原理**：当前 `_significant_overlap` 检测到同行碎片后直接作为"重复"丢弃，但多个变体可能分别识别出同一行的不同部分。应该合并文本而非丢弃。

**实现**：在 `_spatial_dedup` 中，对 `_significant_overlap` 的情况，如果两个块的文本不是子串关系，则按 X 坐标拼接文本。

---

### P1 — 投入中等、效果显著

#### 4.5 ★★★ 升级 PP-OCRv5 模型

**原理**：PP-OCRv5 在文本检测和识别两个环节都有显著改进，尤其是对弯曲文本、小文字、多语言混排的支持。

**实现**：
1. 安装 `rapidocr>=3.5.0`（支持 PP-OCRv5）
2. 在 OCR 引擎初始化时指定 `ocr_version="PP-OCRv5"`
3. 使用 `server` 模型类型替代 `mobile`（精度更高，速度可接受）

**风险**：需要测试兼容性、速度影响，server 模型约比 mobile 大 3-5x

---

#### 4.6 ★★ 增加伽马校正变体

**原理**：不同的伽马值可以增强不同亮度范围的文字对比度。对于中等对比度（灰度标准差 65-100）的场景，CLAHE 和二值化都不触发，伽马校正可以填补空白。

**实现**：`preprocess.py` 增加伽马校正变体

```python
def _gamma_correct(image: np.ndarray, gamma: float = 0.5) -> np.ndarray | None:
    """伽马校正：增强暗部细节。gamma < 1 提亮暗部。"""
    try:
        inv_gamma = 1.0 / gamma
        table = np.array(
            [((i / 255.0) ** inv_gamma) * 255 for i in range(256)]
        ).astype("uint8")
        return cv2.LUT(image, table)
    except Exception:
        return None
```

---

#### 4.7 ★★ 调整 RapidOCR 引擎参数

**原理**：根据 RapidOCR 官方文档，以下参数可以在初始化时配置以提升识别准确性。

**关键调整**：

| 参数 | 当前值 | 建议值 | 理由 |
|------|--------|--------|------|
| `limit_side_len` | 736 (默认) | 960 | 高分辨率屏幕截图需要更大检测尺寸 |
| `unclip_ratio` | 1.6 (默认) | 1.8 | 扩大检测框，减少文字被截断 |
| `text_score` | 0.5 (默认) | 0.35 | 降低最终过滤阈值，减少漏检 |

**实现**：通过 RapidOCR 构造函数或 config.yaml 传入参数

---

#### 4.8 ★★ 多尺度检测策略

**原理**：manga-image-translator 发现 detection_size 与图像分辨率的匹配非常关键。分辨率低时用小 detection_size，分辨率高时用大 detection_size。

**实现**：根据截图大小动态调整 `limit_side_len`

```python
def _adaptive_limit_side_len(image: np.ndarray) -> int:
    h, w = image.shape[:2]
    max_side = max(h, w)
    if max_side < 500:
        return 640
    elif max_side < 1000:
        return 736
    elif max_side < 2000:
        return 960
    else:
        return 1280
```

---

### P2 — 长期优化

#### 4.9 ★ Windows.Media.OCR 作为备选引擎

**原理**：Windows 10+ 内置 OCR 引擎，对屏幕文字（尤其是英文）有不错的识别率。可作为 RapidOCR 的补充/验证引擎。

**实现**：通过 `winocr` Python 包调用 Windows 系统 OCR

---

#### 4.10 ★ LLM 后置纠错

**原理**：利用 LLM 对 OCR 结果进行后处理纠错。将所有 OCR 文本块连同截图一起发送给多模态 LLM，让其纠正识别错误。

**实现**：在翻译前增加一个可选的纠错步骤（会增加一次 API 调用）

---

#### 4.11 ★ 模型微调

**原理**：使用屏幕截图数据对 PP-OCR 的识别模型进行微调。屏幕文字的字体、大小、背景与自然场景文字差异明显，专用模型效果更好。

**实现**：收集屏幕截图数据 → PaddleOCR 训练 → 导出 ONNX → 替换模型文件

---

## 五、实施路线图

| 阶段 | 内容 | 预期效果 |
|------|------|---------|
| **Phase 1** | 4.1 反色变体 + 4.2 纠错字典 + 4.3 翻译 prompt 纠错 | 暗色主题识别 + OCR 错误修正 |
| **Phase 2** | 4.4 同行碎片合并 + 4.7 引擎参数调优 + 4.8 多尺度检测 | 减少漏检和文字丢失 |
| **Phase 3** | 4.5 PP-OCRv5 升级 + 4.6 伽马校正变体 | 整体准确率提升 |
| **Phase 4** | 4.9~4.11 按需选取 | 长期精度优化 |

---

## 六、竞品横向对比 & 最优方案选定

### 6.1 开源项目综合对比

| 维度 | manga-image-translator | Umi-OCR | pot-desktop | RapidOCR (引擎层) |
|------|----------------------|---------|-------------|-------------------|
| **与 Magic Mirror 场景匹配度** | ★★★★★ | ★★★ | ★★ | ★★★★ |
| **OCR 准确性策略丰富度** | ★★★★★ | ★★ | ★★ | ★★★★ |
| **可直接复用的策略数** | 5 项 | 1 项 | 0 项 | 3 项 |
| **实现复杂度** | 低~中 | 低 | 高 | 低 |
| **关注重点** | 图像文字翻译全链路 | 通用 OCR 工具 | 划词翻译+多引擎 | OCR 引擎参数调优 |

**结论：manga-image-translator 是最值得学习的项目。**

理由：
1. **场景最接近**：同样是"截图/图像中的文字 → OCR → 翻译 → 渲染回图像"的全链路，与 Magic Mirror 的 pipeline 几乎一致
2. **策略最丰富且经过验证**：反色、伽马校正、upscale、pre-dict 纠错、动态 detection_size 等策略都在实际翻译场景中验证有效
3. **踩过的坑最有参考价值**：文本颜色提取用 DPGMM 效果不理想（我们已改用中位数方案）、位置精度与文字准确性的取舍、检测框扩展比例等
4. **成熟度高**：9.8k stars，活跃维护，有在线 demo 可对比测试

---

### 6.2 最优单项策略选定

综合评估所有 11 项改进方案的 **投入产出比**：

| 方案 | 实现成本 | 预期收益 | 风险 | 综合评分 |
|------|----------|---------|------|---------|
| 4.1 反色预处理变体 | 极低（~15行） | 极高（暗色主题全面修复） | 极低 | **10/10** |
| 4.3 翻译 prompt 纠错 | 极低（~2行） | 高（LLM 自动修正 OCR 噪声） | 无 | **9/10** |
| 4.2 OCR 纠错字典 | 低（~50行） | 中高（常见错误自动修正） | 低（需防误纠） | 8/10 |
| 4.7 引擎参数调优 | 极低（~3行） | 中高（全面提升检测召回率） | 低 | 8/10 |
| 4.8 多尺度检测 | 低（~20行） | 中（自适应不同分辨率） | 低 | 7/10 |
| 4.4 同行碎片合并 | 中（~40行） | 中（减少文字丢失） | 中（逻辑复杂） | 6/10 |
| 4.6 伽马校正变体 | 极低（~15行） | 中低 | 低 | 6/10 |
| 4.5 PP-OCRv5 升级 | 中（依赖升级+测试） | 高 | 中（兼容性） | 6/10 |
| 4.9 Win OCR 备选 | 高 | 中 | 中 | 4/10 |
| 4.10 LLM 后置纠错 | 中 | 中高 | 高（延迟+费用） | 4/10 |
| 4.11 模型微调 | 极高 | 极高 | 高 | 3/10 |

### 🏆 最优方案：4.1 反色预处理变体

**选定理由**：

1. **覆盖的盲区最大**：当前管线 6 种预处理变体没有一种针对暗色背景。而屏幕翻译场景中暗色主题（IDE、终端、GitHub Dark、Discord 等）占比极高（估计 30-50%），这是最大的系统性盲区
2. **实现成本最低**：仅需在 `preprocess.py` 增加 ~15 行代码，不涉及任何架构改动
3. **零风险**：有条件触发（仅暗色图像），对亮色场景零影响
4. **原理确定**：manga-image-translator 已验证 `det_invert` 对暗色场景的有效性；DB 文本检测器的前景分割模型假设"深色文字+浅色背景"，反色后完全符合这个假设
5. **与我们的设计原则完美契合**：
   - 纯文字场景：反色后文字检出率大幅提升 → 提取准确性↑ → 翻译准确性↑
   - 图文场景：之前完全漏检的暗色区域文字变得可检出 → 不漏识别

**推荐实施顺序**（一次性可完成的组合）：

```
反色变体 (4.1) + prompt 纠错 (4.3) + 引擎参数调优 (4.7)
```

这三项总计改动 < 30 行代码，无依赖关系，可以一次实施并立即生效。

---

## 七、参考资料

| 项目 | 链接 | 说明 |
|------|------|------|
| RapidOCR | https://github.com/RapidAI/RapidOCR | 我们使用的 OCR 引擎 |
| RapidOCR 参数文档 | https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/parameters/ | 所有可调参数说明 |
| PaddleOCR | https://github.com/PaddlePaddle/PaddleOCR | 原始模型来源 |
| Umi-OCR | https://github.com/hiroi-sora/Umi-OCR | 排版解析、忽略区域 |
| manga-image-translator | https://github.com/zyddnys/manga-image-translator | **最值得学习** — 反色/伽马/upscale/pre-dict 策略 |
| pot-desktop | https://github.com/pot-app/pot-desktop | 多引擎备选架构 |
| RapidOCR FAQ | https://rapidai.github.io/RapidOCRDocs/main/faq/faq/ | 边缘文字 padding 等 |
