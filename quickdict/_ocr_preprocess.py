"""
_ocr_preprocess.py — OCR 图像预处理变体生成。

职责单一：接收截图，生成多种预处理变体（numpy array 列表），
供 OcrCapture 多策略重试使用。不含截图、OCR 识别或单词提取逻辑。
"""

import numpy as np

from quickdict.config import logger

# 低分辨率放大倍数
_UPSCALE_FACTOR = 2


def preprocess_variants(img) -> list[np.ndarray]:
    """
    将 PIL Image 转换为多种预处理变体。

    返回 numpy array 列表（BGR），按优先级排列。
    每个变体独立 try/except，单个失败不影响其他。

    变体策略（原始分辨率）：
        ①  原图（保持现有行为）
        ②  灰度 + CLAHE 对比度增强（复杂背景/低对比度）
        ③  灰度 + Otsu 二值化（艺术字/加粗笔画粘连）
        ④  灰度 + 自适应阈值二值化（渐变背景/不均匀光照）
        ⑤  形态学开运算去水平线 + 二值化（下划线干扰）

    变体策略（2× 放大，针对投屏/低分辨率）：
        ⑥  2× 放大（基本放大，使小字达到检测阈值）
        ⑦  2× 放大 + 锐化（抵消投屏/压缩模糊）
        ⑧  2× 放大 + CLAHE（低分辨率 + 低对比度）
    """
    import cv2

    # PIL → numpy BGR（RapidOCR 标准输入格式）
    arr = np.array(img)
    if arr.ndim == 3 and arr.shape[2] == 4:
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    elif arr.ndim == 3:
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    else:
        bgr = arr

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    variants: list[np.ndarray] = []

    # ── 原始分辨率变体 ───────────────────────────────────

    # ── 变体①: 原图 ──────────────────────────────────────
    variants.append(bgr)

    # ── 变体②: CLAHE 对比度增强 ──────────────────────────
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        variants.append(cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR))
    except Exception as e:
        logger.debug("预处理变体② CLAHE 失败: %s", e)

    # ── 变体③: Otsu 二值化 ───────────────────────────────
    try:
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        variants.append(cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR))
    except Exception as e:
        logger.debug("预处理变体③ Otsu 失败: %s", e)

    # ── 变体④: 自适应阈值二值化 ──────────────────────────
    try:
        adaptive = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=15,
            C=8,
        )
        variants.append(cv2.cvtColor(adaptive, cv2.COLOR_GRAY2BGR))
    except Exception as e:
        logger.debug("预处理变体④ 自适应阈值失败: %s", e)

    # ── 变体⑤: 形态学开运算去水平线 + 二值化 ────────────
    try:
        _, bin_for_morph = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        h_kernel_len = max(bgr.shape[1] // 4, 20)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_len, 1))
        h_lines = cv2.morphologyEx(cv2.bitwise_not(bin_for_morph), cv2.MORPH_OPEN, h_kernel)
        cleaned = cv2.add(bin_for_morph, h_lines)
        variants.append(cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR))
    except Exception as e:
        logger.debug("预处理变体⑤ 形态学去下划线失败: %s", e)

    # ── 2× 放大变体（投屏/低分辨率场景）─────────────────

    try:
        upscaled = cv2.resize(
            bgr, None,
            fx=_UPSCALE_FACTOR, fy=_UPSCALE_FACTOR,
            interpolation=cv2.INTER_CUBIC,
        )
        gray_up = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
    except Exception as e:
        logger.debug("2× 放大基础操作失败: %s", e)
        return variants

    # ── 变体⑥: 2× 放大 ──────────────────────────────────
    variants.append(upscaled)

    # ── 变体⑦: 2× 放大 + 锐化 ──────────────────────────
    try:
        sharpen_kernel = np.array([
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0],
        ], dtype=np.float32)
        sharpened = cv2.filter2D(upscaled, -1, sharpen_kernel)
        variants.append(sharpened)
    except Exception as e:
        logger.debug("预处理变体⑦ 放大+锐化失败: %s", e)

    # ── 变体⑧: 2× 放大 + CLAHE ─────────────────────────
    try:
        clahe_up = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced_up = clahe_up.apply(gray_up)
        variants.append(cv2.cvtColor(enhanced_up, cv2.COLOR_GRAY2BGR))
    except Exception as e:
        logger.debug("预处理变体⑧ 放大+CLAHE 失败: %s", e)

    return variants
