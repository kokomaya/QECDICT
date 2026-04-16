"""OCR 图像预处理变体生成。

职责单一：接收 BGR numpy 数组，生成多种预处理变体列表，
供 OCR 引擎多策略重试使用。不含截图、OCR 识别或翻译逻辑。
仅依赖 cv2 和 numpy。
"""

from __future__ import annotations

import logging
from typing import List

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_UPSCALE_FACTOR = 2


def generate_variants(image: np.ndarray) -> List[np.ndarray]:
    """将 BGR 图像转换为少量高质量预处理变体。

    返回 BGR numpy array 列表，按优先级排列。
    每个变体独立 try/except，单个失败不影响其他。

    变体策略（精简版，减少重复识别噪声）：
        ①  原图 BGR
        ②  灰度 + CLAHE 对比度增强
        ③  2× 双三次放大（针对低分辨率文字）

    Args:
        image: BGR 格式 numpy 数组。

    Returns:
        预处理变体列表（均为 BGR numpy 数组）。
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variants: List[np.ndarray] = []

    # ① 原图
    variants.append(image)

    # ② CLAHE 对比度增强
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        variants.append(cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR))
    except Exception as e:
        logger.debug("预处理变体② CLAHE 失败: %s", e)

    # ③ 2× 双三次放大
    try:
        upscaled = cv2.resize(
            image, None,
            fx=_UPSCALE_FACTOR, fy=_UPSCALE_FACTOR,
            interpolation=cv2.INTER_CUBIC,
        )
        variants.append(upscaled)
    except Exception as e:
        logger.debug("预处理变体③ 2x 放大失败: %s", e)

    return variants