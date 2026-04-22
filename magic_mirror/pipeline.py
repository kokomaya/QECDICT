"""翻译管线 — 串联截图→OCR→翻译→排版，只依赖抽象协议。

职责单一：只负责按顺序编排四个步骤，
不 import 任何具体实现类（capture/, ocr/, translation/, layout/）。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, List, Optional, Tuple

from magic_mirror.interfaces import (
    CaptureResult,
    ILayoutEngine,
    IOcrEngine,
    IScreenCapture,
    ITranslator,
    RenderBlock,
    TextBlock,
)

logger = logging.getLogger(__name__)


class TranslatePipeline:
    """截图→OCR→翻译→排版 四步管线。"""

    def __init__(
        self,
        capture: IScreenCapture,
        ocr: IOcrEngine,
        translator: ITranslator,
        layout: ILayoutEngine,
    ) -> None:
        self._capture = capture
        self._ocr = ocr
        self._translator = translator
        self._layout = layout

    def execute(
        self,
        bbox: Tuple[int, int, int, int],
    ) -> Tuple[List[RenderBlock], Tuple[int, int, int, int]]:
        """执行完整翻译管线。

        Args:
            bbox: 屏幕区域 (x, y, w, h)。

        Returns:
            (render_blocks, screen_bbox)

        Raises:
            任一步骤异常时记录日志后原样抛出。
        """
        # 步骤 1: 截图
        t0 = time.perf_counter()
        logger.debug("Pipeline step 1: capture(%s)", bbox)
        result = self._capture.capture(bbox)
        t1 = time.perf_counter()
        logger.info("│ 截图完成  %.0fms  shape=%s", (t1 - t0) * 1000, result.image.shape)

        # 步骤 2: OCR
        logger.debug("Pipeline step 2: recognize")
        text_blocks = self._ocr.recognize(result.image)
        t2 = time.perf_counter()
        logger.info("│ OCR 识别  %.0fms  → %d 个文本块", (t2 - t1) * 1000, len(text_blocks))

        if not text_blocks:
            logger.info("OCR 未识别到文本，跳过翻译和排版")
            return [], result.screen_bbox

        # 将相邻行合并为段落级 TextBlock，提升翻译连贯性
        merged_blocks = _group_text_blocks(text_blocks)

        # 步骤 3: 翻译
        t_tr0 = time.perf_counter()
        logger.debug("Pipeline step 3: translate %d blocks", len(merged_blocks))
        translated = self._translator.translate(merged_blocks)
        t_tr1 = time.perf_counter()
        logger.info("│ 翻译完成  %.0fms  %d 段落", (t_tr1 - t_tr0) * 1000, len(translated))

        # 步骤 4: 排版
        logger.debug("Pipeline step 4: compute_layout")
        render_blocks = self._layout.compute_layout(
            translated, result.image, result.screen_bbox,
        )
        t_ly = time.perf_counter()
        logger.info("│ 排版完成  %.0fms  %d 个渲染块", (t_ly - t_tr1) * 1000, len(render_blocks))
        logger.info("└ 管线总耗时  %.0fms", (t_ly - t0) * 1000)

        return render_blocks, result.screen_bbox

    def execute_from_capture(
        self,
        capture_result: CaptureResult,
    ) -> Tuple[List[RenderBlock], Tuple[int, int, int, int]]:
        """从已有截图结果执行管线（跳过截图步骤）。"""
        result = capture_result

        # 步骤 2: OCR
        t1 = time.perf_counter()
        logger.debug("Pipeline step 2: recognize")
        text_blocks = self._ocr.recognize(result.image)
        t2 = time.perf_counter()
        logger.info("│ OCR 识别  %.0fms  → %d 个文本块", (t2 - t1) * 1000, len(text_blocks))

        if not text_blocks:
            logger.info("OCR 未识别到文本，跳过翻译和排版")
            return [], result.screen_bbox

        # 将相邻行合并为段落级 TextBlock，提升翻译连贯性
        merged_blocks = _group_text_blocks(text_blocks)

        # 步骤 3: 翻译
        t_tr0 = time.perf_counter()
        logger.debug("Pipeline step 3: translate %d blocks", len(merged_blocks))
        translated = self._translator.translate(merged_blocks)
        t_tr1 = time.perf_counter()
        logger.info("│ 翻译完成  %.0fms  %d 段落", (t_tr1 - t_tr0) * 1000, len(translated))

        # 步骤 4: 排版
        logger.debug("Pipeline step 4: compute_layout")
        render_blocks = self._layout.compute_layout(
            translated, result.image, result.screen_bbox,
        )
        t_ly = time.perf_counter()
        logger.info("│ 排版完成  %.0fms  %d 个渲染块", (t_ly - t_tr1) * 1000, len(render_blocks))
        logger.info("└ 管线总耗时  %.0fms (不含截图)", (t_ly - t1) * 1000)

        return render_blocks, result.screen_bbox

    def execute_streaming_from_capture(
        self,
        capture_result: CaptureResult,
        on_block_ready: Callable[[RenderBlock], None],
        on_ocr_done: Optional[Callable[[List[TextBlock]], None]] = None,
    ) -> Tuple[int, int, int, int]:
        """流式管线：OCR → 逐条翻译 → 逐条排版 → 回调。

        每翻译完一条即计算该条的排版并通过 on_block_ready 回调通知调用方，
        实现渐进渲染。

        Args:
            capture_result: 已截取的图像。
            on_block_ready: 每个 RenderBlock 就绪时的回调。
            on_ocr_done: OCR 完成后、翻译开始前的回调（用于骨架屏）。

        Returns:
            screen_bbox。
        """
        result = capture_result

        # 步骤 2: OCR
        t_ocr0 = time.perf_counter()
        logger.debug("Streaming pipeline step 2: recognize")
        text_blocks = self._ocr.recognize(result.image)
        t_ocr1 = time.perf_counter()
        logger.info("│ [流式] OCR 识别  %.0fms  → %d 个文本块",
                     (t_ocr1 - t_ocr0) * 1000, len(text_blocks))

        if not text_blocks:
            logger.info("OCR 未识别到文本")
            return result.screen_bbox

        # 通知调用方 OCR 完成（用原始 blocks 显示骨架屏）
        if on_ocr_done is not None:
            on_ocr_done(text_blocks)

        # 将相邻行合并为段落级 TextBlock，提升翻译连贯性
        merged_blocks = _group_text_blocks(text_blocks)
        logger.debug("  grouped %d text blocks into %d paragraphs",
                     len(text_blocks), len(merged_blocks))
        for i, mb in enumerate(merged_blocks):
            logger.debug("  paragraph #%d: %s", i + 1, mb.text[:80])

        # 步骤 3+4: 逐段翻译 + 排版
        t_tr0 = time.perf_counter()
        logger.debug("Streaming pipeline step 3+4: translate_stream + layout")
        emitted = 0
        for translated_block in self._translator.translate_stream(merged_blocks):
            render_blocks = self._layout.compute_layout(
                [translated_block], result.image, result.screen_bbox,
            )
            for rb in render_blocks:
                on_block_ready(rb)
                emitted += 1

        t_end = time.perf_counter()
        logger.info("│ [流式] 翻译+排版  %.0fms  %d 个渲染块",
                     (t_end - t_tr0) * 1000, emitted)
        logger.info("└ [流式] 管线总耗时  %.0fms", (t_end - t_ocr0) * 1000)
        return result.screen_bbox


# ------------------------------------------------------------------
# 段落预分组
# ------------------------------------------------------------------

# 相邻 TextBlock 的 Y 间距低于此比例（相对行高）时合并为同一段落
_PARA_MERGE_Y_GAP = 0.5
# 字号差异超过此比例则视为不同层级（如标题 vs 正文），不合并
_FONT_SIZE_RATIO_THRESHOLD = 0.25
# 单组最大行数，防止整页合并为一个块
_MAX_GROUP_LINES = 4
# 列表项前缀（文本以这些开头时独立成段）
_LIST_PREFIXES = ("•", "·", "-", "–", "—", "*", "►", "▪", "■", "○", "●")
# 左缩进变化超过此像素数则视为不同层级，不合并
_INDENT_SHIFT_PX = 15
# 数字编号列表正则
_RE_NUMBERED_LIST = re.compile(r"^\s*\d+[\.\)]\s")


def _group_text_blocks(text_blocks: List[TextBlock]) -> List[TextBlock]:
    """将相邻的 OCR 文本块按段落合并，减少翻译碎片化。

    合并条件：
      - Y 间距小（同段落连续行）
      - X 范围有重叠（同列）
      - 字号相近（排除标题与正文混合）
      - 非列表项开头
      - 未超过组内最大行数
    """
    if len(text_blocks) <= 1:
        return list(text_blocks)

    sorted_blocks = sorted(
        text_blocks, key=lambda b: min(pt[1] for pt in b.bbox),
    )
    groups: List[List[TextBlock]] = [[sorted_blocks[0]]]

    for blk in sorted_blocks[1:]:
        if (len(groups[-1]) < _MAX_GROUP_LINES
                and _should_merge_tb(groups[-1][-1], blk)):
            groups[-1].append(blk)
        else:
            groups.append([blk])

    return [_merge_tb_group(g) for g in groups]


def _should_merge_tb(a: TextBlock, b: TextBlock) -> bool:
    """判断两个相邻 TextBlock 是否应合并为同一段落。"""
    b_text = b.text.strip()

    # 列表项独立成段：bullet 前缀
    if b_text and b_text[0] in _LIST_PREFIXES:
        return False

    # 列表项独立成段：数字编号 (1. 2. 3) ...)
    if _RE_NUMBERED_LIST.match(b_text):
        return False
    if _RE_NUMBERED_LIST.match(a.text.strip()):
        return False

    # 字号差异检查：防止标题与正文合并
    max_fs = max(a.font_size_est, b.font_size_est)
    if max_fs > 0:
        ratio = abs(a.font_size_est - b.font_size_est) / max_fs
        if ratio > _FONT_SIZE_RATIO_THRESHOLD:
            return False

    a_xs = [pt[0] for pt in a.bbox]
    b_xs = [pt[0] for pt in b.bbox]

    # 缩进变化检查：左边距偏移大 → 不同层级
    a_left = min(a_xs)
    b_left = min(b_xs)
    if abs(a_left - b_left) > _INDENT_SHIFT_PX:
        return False

    a_ys = [pt[1] for pt in a.bbox]
    a_top, a_bottom = min(a_ys), max(a_ys)
    a_h = max(a_bottom - a_top, 1)

    b_ys = [pt[1] for pt in b.bbox]
    b_top = min(b_ys)

    # Y 间距检查
    if b_top - a_bottom > a_h * _PARA_MERGE_Y_GAP:
        return False

    # X 重叠检查
    overlap = min(max(a_xs), max(b_xs)) - max(a_left, b_left)
    return overlap > 0


def _merge_tb_group(blocks: List[TextBlock]) -> TextBlock:
    """将一组 TextBlock 合并为单个段落级 TextBlock。"""
    if len(blocks) == 1:
        text = _cleanup_ocr_text(blocks[0].text)
        if text != blocks[0].text:
            return TextBlock(
                text=text,
                bbox=blocks[0].bbox,
                font_size_est=blocks[0].font_size_est,
                confidence=blocks[0].confidence,
            )
        return blocks[0]

    combined_text = _cleanup_ocr_text(" ".join(b.text for b in blocks))

    all_pts = [pt for b in blocks for pt in b.bbox]
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    merged_bbox = [
        [min(xs), min(ys)],
        [max(xs), min(ys)],
        [max(xs), max(ys)],
        [min(xs), max(ys)],
    ]

    avg_font = sum(b.font_size_est for b in blocks) / len(blocks)
    min_conf = min(b.confidence for b in blocks)

    return TextBlock(
        text=combined_text,
        bbox=merged_bbox,
        font_size_est=avg_font,
        confidence=min_conf,
    )


# ------------------------------------------------------------------
# OCR 文本清洗（合并后执行）
# ------------------------------------------------------------------

# PDF 断行连字符: "com- munication" → "communication"
_RE_HYPHEN_BREAK = re.compile(r"(\w)- +(\w)")
# 匹配 4+ 连续纯字母序列
_RE_LONG_ALPHA = re.compile(r"[A-Za-z]{4,}")
# 标点紧跟字母:  "data.The" → "data. The"
_RE_PUNCT_WORD = re.compile(r"([.!?;,])([A-Za-z])")
# 右括号紧跟字母 / 字母紧跟左括号
_RE_PAREN_WORD = re.compile(r"(\))([A-Za-z])")
_RE_WORD_PAREN = re.compile(r"([A-Za-z])(\()")


def _cleanup_ocr_text(text: str) -> str:
    """合并后的 OCR 文本清洗。

    1. 修复 PDF 断行连字符（"com- munication" → "communication"）
    2. 合并 OCR 音节碎片（"communi cation" → "communication"）
    3. 修复标点-字母粘连
    4. 用 wordninja 拆分粘连的多个单词
    """
    if not text or len(text) < 4:
        return text

    # 1. 修复断行连字符
    t = _RE_HYPHEN_BREAK.sub(r"\1\2", text)

    # 2. 合并音节碎片
    t = _rejoin_fragments(t)

    # 3. 标点边界
    t = _RE_PUNCT_WORD.sub(r"\1 \2", t)
    t = _RE_PAREN_WORD.sub(r"\1 \2", t)
    t = _RE_WORD_PAREN.sub(r"\1 \2", t)

    # 4. wordninja 拆分粘连词
    t = _RE_LONG_ALPHA.sub(_segment_long_run, t)

    return t


def _rejoin_fragments(text: str) -> str:
    """贪心合并 OCR 音节碎片。

    对空格分隔的 token，尝试将相邻 2~4 个纯字母 token 拼接，
    若 wordninja 认为拼接结果是一个完整单词则合并。
    """
    import wordninja  # 惰性导入

    tokens = text.split()
    if len(tokens) <= 1:
        return text

    result: List[str] = []
    i = 0
    while i < len(tokens):
        best_len = 1
        for k in range(min(4, len(tokens) - i), 1, -1):
            group = tokens[i : i + k]
            if not all(t.isalpha() for t in group):
                continue
            joined = "".join(group)
            parts = wordninja.split(joined)
            if len(parts) == 1:
                best_len = k
                break
        if best_len > 1:
            result.append("".join(tokens[i : i + best_len]))
        else:
            result.append(tokens[i])
        i += best_len
    return " ".join(result)


def _segment_long_run(match: re.Match) -> str:  # type: ignore[type-arg]
    """将一段 4+ 字符的纯字母序列用 wordninja 拆分。"""
    import wordninja  # 惰性导入

    run = match.group()
    parts = wordninja.split(run)
    if len(parts) >= 2:
        return " ".join(parts)
    return run