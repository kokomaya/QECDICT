"""翻译管线 — 串联截图→OCR→翻译→排版，只依赖抽象协议。

职责单一：只负责按顺序编排四个步骤，
不 import 任何具体实现类（capture/, ocr/, translation/, layout/）。
"""

from __future__ import annotations

import logging
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
        logger.debug("Pipeline step 1: capture(%s)", bbox)
        result = self._capture.capture(bbox)
        logger.debug("  captured image shape: %s", result.image.shape)

        # 步骤 2: OCR
        logger.debug("Pipeline step 2: recognize")
        text_blocks = self._ocr.recognize(result.image)
        logger.debug("  recognized %d text blocks", len(text_blocks))

        if not text_blocks:
            logger.info("OCR 未识别到文本，跳过翻译和排版")
            return [], result.screen_bbox

        # 将相邻行合并为段落级 TextBlock，提升翻译连贯性
        merged_blocks = _group_text_blocks(text_blocks)

        # 步骤 3: 翻译
        logger.debug("Pipeline step 3: translate %d blocks", len(merged_blocks))
        translated = self._translator.translate(merged_blocks)
        logger.debug("  translated %d blocks", len(translated))

        # 步骤 4: 排版
        logger.debug("Pipeline step 4: compute_layout")
        render_blocks = self._layout.compute_layout(
            translated, result.image, result.screen_bbox,
        )
        logger.debug("  computed %d render blocks", len(render_blocks))

        return render_blocks, result.screen_bbox

    def execute_from_capture(
        self,
        capture_result: CaptureResult,
    ) -> Tuple[List[RenderBlock], Tuple[int, int, int, int]]:
        """从已有截图结果执行管线（跳过截图步骤）。"""
        result = capture_result

        # 步骤 2: OCR
        logger.debug("Pipeline step 2: recognize")
        text_blocks = self._ocr.recognize(result.image)
        logger.debug("  recognized %d text blocks", len(text_blocks))

        if not text_blocks:
            logger.info("OCR 未识别到文本，跳过翻译和排版")
            return [], result.screen_bbox

        # 将相邻行合并为段落级 TextBlock，提升翻译连贯性
        merged_blocks = _group_text_blocks(text_blocks)

        # 步骤 3: 翻译
        logger.debug("Pipeline step 3: translate %d blocks", len(merged_blocks))
        translated = self._translator.translate(merged_blocks)
        logger.debug("  translated %d blocks", len(translated))

        # 步骤 4: 排版
        logger.debug("Pipeline step 4: compute_layout")
        render_blocks = self._layout.compute_layout(
            translated, result.image, result.screen_bbox,
        )
        logger.debug("  computed %d render blocks", len(render_blocks))

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
        logger.debug("Streaming pipeline step 2: recognize")
        text_blocks = self._ocr.recognize(result.image)
        logger.debug("  recognized %d text blocks", len(text_blocks))

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

        # 步骤 3+4: 逐段翻译 + 排版
        logger.debug("Streaming pipeline step 3+4: translate_stream + layout")
        emitted = 0
        for translated_block in self._translator.translate_stream(merged_blocks):
            render_blocks = self._layout.compute_layout(
                [translated_block], result.image, result.screen_bbox,
            )
            for rb in render_blocks:
                on_block_ready(rb)
                emitted += 1

        logger.debug("  streamed %d render blocks", emitted)
        return result.screen_bbox


# ------------------------------------------------------------------
# 段落预分组
# ------------------------------------------------------------------

# 相邻 TextBlock 的 Y 间距低于此比例（相对行高）时合并为同一段落
_PARA_MERGE_Y_GAP = 0.5
# 字号差异超过此比例则视为不同层级（如标题 vs 正文），不合并
_FONT_SIZE_RATIO_THRESHOLD = 0.25
# 单组最大行数，防止整页合并为一个块
_MAX_GROUP_LINES = 6
# 列表项前缀（文本以这些开头时独立成段）
_LIST_PREFIXES = ("•", "·", "-", "–", "—", "*", "►", "▪", "■", "○", "●")


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
    # 列表项独立成段
    b_text = b.text.strip()
    if b_text and b_text[0] in _LIST_PREFIXES:
        return False

    # 字号差异检查：防止标题与正文合并
    max_fs = max(a.font_size_est, b.font_size_est)
    if max_fs > 0:
        ratio = abs(a.font_size_est - b.font_size_est) / max_fs
        if ratio > _FONT_SIZE_RATIO_THRESHOLD:
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
    a_xs = [pt[0] for pt in a.bbox]
    b_xs = [pt[0] for pt in b.bbox]
    overlap = min(max(a_xs), max(b_xs)) - max(min(a_xs), min(b_xs))
    return overlap > 0


def _merge_tb_group(blocks: List[TextBlock]) -> TextBlock:
    """将一组 TextBlock 合并为单个段落级 TextBlock。"""
    if len(blocks) == 1:
        return blocks[0]

    combined_text = " ".join(b.text for b in blocks)

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