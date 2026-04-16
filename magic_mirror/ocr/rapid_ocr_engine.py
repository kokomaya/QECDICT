"""OCR 识别引擎 — IOcrEngine 的 RapidOCR 实现。

职责单一：接收 BGR 图像，返回带坐标的文本块列表。
不涉及截图、翻译、排版或渲染逻辑。
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np

from magic_mirror.config.settings import OCR_CONFIDENCE_THRESHOLD, OCR_DET_BOX_THRESH
from magic_mirror.interfaces.types import TextBlock
from magic_mirror.ocr.preprocess import generate_variants

logger = logging.getLogger(__name__)


class RapidOcrEngine:
    """IOcrEngine 实现 — 使用 RapidOCR (ONNX Runtime) 进行文字识别。

    惰性加载模型：首次调用 recognize() 时才初始化 OCR 引擎，
    避免启动时占用内存和加载时间。
    """

    def __init__(self) -> None:
        self._ocr = None
        self._available: bool | None = None  # None = 尚未检测

    def recognize(self, image: np.ndarray) -> List[TextBlock]:
        """从图像中提取带位置信息的文本块。

        对图像生成多种预处理变体，逐一识别并合并结果（按文本去重）。

        Args:
            image: BGR 格式 numpy 数组。

        Returns:
            识别到的文本块列表，按 Y 坐标从上到下排序。
        """
        if not self._ensure_available():
            return []

        variants = generate_variants(image)
        seen_texts: set[str] = set()
        blocks: List[TextBlock] = []

        for variant in variants:
            raw = self._run_ocr(variant)
            if not raw:
                continue
            for bbox_points, text, confidence in raw:
                text = text.strip()
                if not text:
                    continue
                if confidence < OCR_CONFIDENCE_THRESHOLD:
                    continue
                if text in seen_texts:
                    continue
                seen_texts.add(text)
                blocks.append(TextBlock(
                    text=text,
                    bbox=bbox_points,
                    font_size_est=self._estimate_font_size(bbox_points),
                    confidence=confidence,
                ))

        # 按 Y 坐标（bbox 左上角）排序，从上到下
        blocks.sort(key=lambda b: b.bbox[0][1])

        logger.debug("OCR 识别到 %d 个文本块", len(blocks))
        return blocks

    # ── 惰性加载 ──

    def _ensure_available(self) -> bool:
        """检查并惰性加载 OCR 引擎。加载失败后不再重试。"""
        if self._available is False:
            return False
        if self._ocr is not None:
            return True
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR(det_box_thresh=OCR_DET_BOX_THRESH)
            self._available = True
            logger.info("OCR 引擎已加载")
            return True
        except Exception as e:
            self._available = False
            logger.warning("OCR 引擎不可用: %s", e)
            return False

    # ── OCR 调用 ──

    def _run_ocr(self, image: np.ndarray) -> list[tuple] | None:
        """调用 RapidOCR 执行识别。

        Returns:
            [(bbox_points, text, confidence), ...] 或 None。
        """
        try:
            result, _ = self._ocr(image)
            return result if result else None
        except Exception as e:
            logger.debug("OCR 调用异常: %s", e)
            return None

    # ── 字号估算 ──

    @staticmethod
    def _estimate_font_size(bbox: list[list[float]]) -> float:
        """根据 bbox 高度估算字号（像素）。

        bbox 四角坐标: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        字号 ≈ 左上到左下的垂直距离。
        """
        return abs(bbox[3][1] - bbox[0][1])