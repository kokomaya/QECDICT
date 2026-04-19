## Plan: OCR 取词增强 — 复杂场景预处理

当前 OCR 管线对截图**零预处理**，原图直传 RapidOCR，这是复杂场景识别率低的根本原因。方案：引入**多策略图像预处理 + 自动重试**，截图一次后依次尝试多种预处理变体直到成功，用户无需反复触发。

---

### Phase 1: 图像预处理管线（核心）

1. **添加 `opencv-python>=4.8` 到依赖** — [requirements.txt](quickdict/requirements.txt)（release 已捆绑 cv2）
2. **新增 `_preprocess_variants()` 方法** — [_ocr_capture.py](quickdict/_ocr_capture.py)，接收 PIL Image，返回多个预处理变体:
   - 变体①: 原图（保持现有行为）
   - 变体②: 灰度 + CLAHE 对比度增强（解决复杂背景/低对比度）
   - 变体③: 灰度 + Otsu 二值化（解决艺术字/加粗笔画粘连）
   - 变体④: 灰度 + 自适应阈值二值化（解决渐变背景/不均匀光照）
   - 变体⑤: 形态学开运算（移除水平下划线干扰）
3. **修改 `capture()` 为多策略重试** — *depends on 2*，截图一次 → 生成变体 → 依次识别 → 首个有效结果即返回

### Phase 2: RapidOCR 参数调优（辅助提升，*parallel with Phase 1*）

4. **放宽检测阈值** — 修改 RapidOCR 初始化参数:
   - `det_box_thresh`: 0.5 → 0.3（更多候选文本框）
   - `det_unclip_ratio`: 1.6 → 2.0（扩大检测框包含完整字符）
   - 代码中 `_MIN_CONFIDENCE`: 0.35 → 0.25

### Phase 3: 截图区域扩大（辅助提升，*parallel with Phase 1*）

5. **扩大截取范围** — `_HALF_W`: 160→200，`_HALF_H`: 60→80，为 det 模块提供更多上下文

### Phase 4: 倾斜校正（可选增强，*depends on Phase 1*）

6. **轻量仿射变换校正** — 用 `cv2.minAreaRect` 检测倾斜角度，对 ±5°~±30° 文本做透视校正，作为额外变体插入

---

**Relevant files**
- [quickdict/_ocr_capture.py](quickdict/_ocr_capture.py) — 截图调度 + 多策略重试 + dxcam 回退 + Y 加权选词
- [quickdict/_ocr_preprocess.py](quickdict/_ocr_preprocess.py) — 图像预处理变体（8 种：原图/CLAHE/Otsu/自适应/形态学 + 2× 放大×3）
- [quickdict/_capture_overlay.py](quickdict/_capture_overlay.py) — 截图区域可视化（调试开关）
- [quickdict/requirements.txt](quickdict/requirements.txt) — opencv-python + dxcam

**实施状态**
- Phase 1 (预处理管线): ✅ 已完成
- Phase 2 (参数调优): ✅ 已完成
- Phase 3 (截图扩大): ✅ 已完成
- Phase 4 (倾斜校正): ⬜ 待评估
- 额外: dxcam 硬件加速窗口回退 ✅ | 多显示器坐标修复 ✅ | 2× 放大变体 ✅ | Y 加权选词 ✅

**Verification**
1. 准备困难场景截图（倾斜字幕、艺术字、下划线文字、复杂背景），对比 before/after
2. 手动测试: YouTube 字幕、PPT 艺术字、IDE 下划线代码、网页图片文字
3. 性能: 单次取词目标 < 500ms（多数情况第 1-2 个变体即命中）
4. 回归: 原有正常场景仍首次命中，无降级

**Decisions**
- 不替换 OCR 模型（PP-OCRv4 已是最优，保留中英混合能力）
- 多变体串行 fail-fast，非并行（避免内存开销）
- Phase 4 先评估 Phase 1-3 效果后再决定
