"""翻译管线 — 串联截图→OCR→翻译→排版，只依赖抽象协议。

职责单一：只负责按顺序编排四个步骤，
不 import 任何具体实现类（capture/, ocr/, translation/, layout/）。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from magic_mirror.interfaces import (
    CaptureResult,
    ILayoutEngine,
    IOcrEngine,
    IScreenCapture,
    ITranslator,
    RenderBlock,
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

        # 步骤 3: 翻译
        logger.debug("Pipeline step 3: translate %d blocks", len(text_blocks))
        translated = self._translator.translate(text_blocks)
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

        # 步骤 3: 翻译
        logger.debug("Pipeline step 3: translate %d blocks", len(text_blocks))
        translated = self._translator.translate(text_blocks)
        logger.debug("  translated %d blocks", len(translated))

        # 步骤 4: 排版
        logger.debug("Pipeline step 4: compute_layout")
        render_blocks = self._layout.compute_layout(
            translated, result.image, result.screen_bbox,
        )
        logger.debug("  computed %d render blocks", len(render_blocks))

        return render_blocks, result.screen_bbox