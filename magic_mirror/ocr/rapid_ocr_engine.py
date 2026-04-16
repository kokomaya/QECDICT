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
        candidates: List[TextBlock] = []

        # 第一个变体是原图，用于计算缩放比例
        orig_h, orig_w = image.shape[:2]

        for variant in variants:
            raw = self._run_ocr(variant)
            if not raw:
                continue

            # 如果变体尺寸与原图不同，需要缩放 bbox 坐标回原图尺寸
            vh, vw = variant.shape[:2]
            scale_x = orig_w / vw if vw != orig_w else 1.0
            scale_y = orig_h / vh if vh != orig_h else 1.0

            for bbox_points, text, confidence in raw:
                text = text.strip()
                if not text:
                    continue
                if confidence < OCR_CONFIDENCE_THRESHOLD:
                    continue

                # 缩放 bbox 回原图坐标
                if scale_x != 1.0 or scale_y != 1.0:
                    bbox_points = [
                        [pt[0] * scale_x, pt[1] * scale_y]
                        for pt in bbox_points
                    ]

                candidates.append(TextBlock(
                    text=text,
                    bbox=bbox_points,
                    font_size_est=self._estimate_font_size(bbox_points),
                    confidence=confidence,
                ))

        # 空间去重：重叠区域 IoU > 阈值时只保留置信度最高的
        blocks = self._spatial_dedup(candidates)

        # 按 Y 坐标（bbox 左上角）排序，从上到下
        blocks.sort(key=lambda b: b.bbox[0][1])

        logger.debug("OCR 识别到 %d 个文本块 (候选 %d)", len(blocks), len(candidates))
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
    def _spatial_dedup(
        candidates: List[TextBlock],
        iou_threshold: float = 0.3,
    ) -> List[TextBlock]:
        """空间去重：对重叠的文本块只保留置信度最高的。

        两个 bbox 的 IoU（交集/并集）超过阈值时认为重复。
        """
        # 按置信度降序排列，优先保留高置信度
        sorted_cands = sorted(candidates, key=lambda b: b.confidence, reverse=True)
        kept: List[TextBlock] = []

        for cand in sorted_cands:
            r1 = _bbox_to_rect(cand.bbox)
            is_dup = False
            for existing in kept:
                r2 = _bbox_to_rect(existing.bbox)
                if _iou(r1, r2) > iou_threshold:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(cand)

        return kept

    @staticmethod
    def _estimate_font_size(bbox: list[list[float]]) -> float:
        """根据 bbox 高度估算字号（像素）。

        bbox 四角坐标: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        字号 ≈ 左上到左下的垂直距离。
        """
        return abs(bbox[3][1] - bbox[0][1])


# ------------------------------------------------------------------
# 模块级辅助
# ------------------------------------------------------------------

def _bbox_to_rect(bbox: list) -> tuple:
    """四角坐标 → (x_min, y_min, x_max, y_max)。"""
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    return (min(xs), min(ys), max(xs), max(ys))


def _iou(r1: tuple, r2: tuple) -> float:
    """计算两个轴对齐矩形的 IoU (Intersection over Union)。"""
    x1 = max(r1[0], r2[0])
    y1 = max(r1[1], r2[1])
    x2 = min(r1[2], r2[2])
    y2 = min(r1[3], r2[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0

    area1 = (r1[2] - r1[0]) * (r1[3] - r1[1])
    area2 = (r2[2] - r2[0]) * (r2[3] - r2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0