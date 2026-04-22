"""OCR 图像预处理变体生成。

职责单一：接收 BGR numpy 数组，生成多种预处理变体列表，
供 OCR 引擎多策略重试使用。不含截图、OCR 识别或翻译逻辑。
仅依赖 cv2 和 numpy。

变体策略：
  1. 原图
  2. CLAHE 对比度增强（提升低对比度文字识别率）
  3. 锐化（提升模糊文字识别率）
  4. 多级放大（低分辨率文字）
  5. 自适应二值化（极低对比度场景）
  6. 边界填充（提升边缘文字检测率）
  7. 反色（适用于暗色主题：IDE、终端、深色网页等）
  8. 伽马校正（增强中等对比度场景的暗部细节）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

from magic_mirror.config.settings import OCR_PAD_BORDER

logger = logging.getLogger(__name__)

# 低分辨率阈值：低于此高度生成 2× 放大变体
_UPSCALE_THRESHOLD = 120
# 极低分辨率阈值：低于此高度额外生成 3× 放大变体
_UPSCALE_TINY_THRESHOLD = 50
# 低对比度阈值：灰度标准差低于此值时生成二值化变体
_LOW_CONTRAST_STD = 50


@dataclass
class VariantInfo:
    """预处理变体及其坐标偏移信息。"""
    image: np.ndarray
    offset_x: float = 0.0
    offset_y: float = 0.0


def generate_variants(image: np.ndarray) -> List[VariantInfo]:
    """将 BGR 图像转换为多种预处理变体列表。

    返回 VariantInfo 列表，按优先级排列。
    每个变体包含坐标偏移信息以支持边界填充等变换。

    Args:
        image: BGR 格式 numpy 数组。

    Returns:
        预处理变体列表。
    """
    variants: List[VariantInfo] = [VariantInfo(image=image)]
    h = image.shape[0]

    # ── 1. CLAHE 对比度增强 ──
    clahe_img = _apply_clahe(image)
    if clahe_img is not None:
        variants.append(VariantInfo(image=clahe_img))

    # ── 2. 锐化 ──
    sharp_img = _sharpen(image)
    if sharp_img is not None:
        variants.append(VariantInfo(image=sharp_img))

    # ── 3. 多级放大（低分辨率文字） ──
    if h < _UPSCALE_THRESHOLD:
        up2 = _upscale(image, 2)
        if up2 is not None:
            variants.append(VariantInfo(image=up2))
        if h < _UPSCALE_TINY_THRESHOLD:
            up3 = _upscale(image, 3)
            if up3 is not None:
                variants.append(VariantInfo(image=up3))

    # ── 4. 自适应二值化（低对比度场景） ──
    bin_img = _adaptive_binarize(image)
    if bin_img is not None:
        variants.append(VariantInfo(image=bin_img))

    # ── 5. 边界填充（提升边缘文字检测率） ──
    pad = OCR_PAD_BORDER
    if pad > 0:
        padded = _pad_border(image, pad)
        if padded is not None:
            variants.append(VariantInfo(
                image=padded, offset_x=float(pad), offset_y=float(pad),
            ))

    # ── 6. 反色（暗色主题：亮字暗底） ──
    inv_img = _invert(image)
    if inv_img is not None:
        variants.append(VariantInfo(image=inv_img))

    # ── 7. 伽马校正（中等对比度增强） ──
    gamma_img = _gamma_correct(image)
    if gamma_img is not None:
        variants.append(VariantInfo(image=gamma_img))

    return variants


# ------------------------------------------------------------------
# 内部变体生成函数
# ------------------------------------------------------------------

def _apply_clahe(image: np.ndarray) -> np.ndarray | None:
    """CLAHE 对比度增强：在 LAB 空间对 L 通道做自适应直方图均衡。"""
    try:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception as e:
        logger.debug("CLAHE 增强失败: %s", e)
        return None


def _sharpen(image: np.ndarray) -> np.ndarray | None:
    """Unsharp Mask 锐化：突出文字边缘。"""
    try:
        blurred = cv2.GaussianBlur(image, (0, 0), 3)
        return cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
    except Exception as e:
        logger.debug("锐化失败: %s", e)
        return None


def _upscale(image: np.ndarray, factor: int) -> np.ndarray | None:
    """双三次插值放大。"""
    try:
        return cv2.resize(
            image, None,
            fx=factor, fy=factor,
            interpolation=cv2.INTER_CUBIC,
        )
    except Exception as e:
        logger.debug("%dx 放大失败: %s", factor, e)
        return None


def _adaptive_binarize(image: np.ndarray) -> np.ndarray | None:
    """自适应二值化：仅在低对比度场景生成。

    将灰度图做 Gaussian 自适应阈值处理，转回 BGR 供 OCR 使用。
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if gray.std() >= _LOW_CONTRAST_STD:
            return None  # 对比度足够，不需要二值化
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2,
        )
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    except Exception as e:
        logger.debug("自适应二值化失败: %s", e)
        return None


def _pad_border(image: np.ndarray, pad: int = 12) -> np.ndarray | None:
    """白色边界填充：提升边缘文字检测率。"""
    try:
        return cv2.copyMakeBorder(
            image, pad, pad, pad, pad,
            cv2.BORDER_CONSTANT, value=(255, 255, 255),
        )
    except Exception as e:
        logger.debug("边界填充失败: %s", e)
        return None


def _invert(image: np.ndarray) -> np.ndarray | None:
    """反色：适用于亮字暗底场景（IDE、终端等暗色主题）。

    仅当图像整体偏暗（平均亮度 < 127）时生成，
    避免对亮色场景产生冗余变体。
    参考 manga-image-translator 的 det_invert 策略。
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if gray.mean() >= 127:
            return None  # 亮色背景，不需要反色
        return cv2.bitwise_not(image)
    except Exception as e:
        logger.debug("反色失败: %s", e)
        return None


def _gamma_correct(image: np.ndarray, gamma: float = 0.5) -> np.ndarray | None:
    """伽马校正：增强暗部细节。

    gamma < 1 提亮暗部，适合中等对比度场景。
    仅当灰度标准差在 [40, 100] 之间时生成（过低已有二值化，过高无需增强）。
    参考 manga-image-translator 的 det_gamma_correct 策略。
    """
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        std = gray.std()
        if std < 40 or std > 100:
            return None
        inv_gamma = 1.0 / gamma
        table = np.array(
            [((i / 255.0) ** inv_gamma) * 255 for i in range(256)]
        ).astype("uint8")
        return cv2.LUT(image, table)
    except Exception as e:
        logger.debug("伽马校正失败: %s", e)
        return None