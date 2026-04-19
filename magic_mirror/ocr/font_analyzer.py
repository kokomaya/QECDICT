"""字体属性分析器 — 从图像像素检测 bold/serif/italic。

仅依赖 cv2 和 numpy，不涉及 Qt 或字体映射。
"""

from __future__ import annotations

import logging
from typing import List

import cv2
import numpy as np

from magic_mirror.config.settings import (
    FONT_BOLD_THRESHOLD,
    FONT_ITALIC_THRESHOLD,
    FONT_SERIF_CV_THRESHOLD,
)
from magic_mirror.interfaces.types import FontInfo

logger = logging.getLogger(__name__)

_MIN_FONT_SIZE_FOR_ANALYSIS = 10


def analyze_font(
    image: np.ndarray,
    bbox: List[List[float]],
    font_size_est: float,
) -> FontInfo:
    """从 bbox 区域的像素分析字体属性。

    Args:
        image: BGR 格式原始图像。
        bbox: 四角坐标。
        font_size_est: OCR 估算字号（像素）。

    Returns:
        FontInfo 包含 is_bold, is_serif, is_italic 及辅助数据。
    """
    if font_size_est < _MIN_FONT_SIZE_FOR_ANALYSIS:
        return FontInfo()

    region = _extract_region(image, bbox)
    if region is None or region.shape[0] < 5 or region.shape[1] < 5:
        return FontInfo()

    binary = _binarize(region)
    if binary is None:
        return FontInfo()

    fg_count = int(np.count_nonzero(binary))
    if fg_count < 20:
        return FontInfo()

    is_bold, stroke_w = _detect_bold(binary, font_size_est)
    is_serif = _detect_serif(binary)
    is_italic, skew = _detect_italic(binary, font_size_est)

    confidence = min(1.0, fg_count / 200.0)

    return FontInfo(
        is_serif=is_serif,
        is_bold=is_bold,
        is_italic=is_italic,
        stroke_width=stroke_w,
        skew_angle=skew,
        confidence=confidence,
    )


def _extract_region(
    image: np.ndarray, bbox: List[List[float]],
) -> np.ndarray | None:
    h, w = image.shape[:2]
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    x1 = max(int(min(xs)), 0)
    y1 = max(int(min(ys)), 0)
    x2 = min(int(max(xs)), w)
    y2 = min(int(max(ys)), h)
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


def _binarize(region: np.ndarray) -> np.ndarray | None:
    """Otsu 二值化，前景为白色（255）。"""
    try:
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )
        fg = int(np.count_nonzero(binary))
        total = binary.size
        if fg > total * 0.7:
            binary = cv2.bitwise_not(binary)
        return binary
    except Exception:
        return None


# ── Bold 检测：距离变换 ──

def _detect_bold(
    binary: np.ndarray, font_size_est: float,
) -> tuple[bool, float]:
    """通过距离变换计算平均半笔画宽度，判断是否粗体。"""
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    fg_mask = binary > 0
    if not np.any(fg_mask):
        return False, 0.0

    mean_dist = float(np.mean(dist[fg_mask]))
    ratio = mean_dist / font_size_est if font_size_est > 0 else 0.0

    return ratio > FONT_BOLD_THRESHOLD, mean_dist


# ── Serif 检测：run-length 变异系数 ──

def _detect_serif(binary: np.ndarray) -> bool:
    """分析基线区域的水平 run-length 分布，判断是否衬线体。"""
    h, w = binary.shape

    # 采样底部 20% 和顶部 15%
    zones = [
        binary[int(h * 0.80):, :],  # baseline
        binary[:int(h * 0.15), :],  # cap-line
    ]

    max_cv = 0.0
    for zone in zones:
        runs = _horizontal_runs(zone)
        if len(runs) < 5:
            continue
        arr = np.array(runs, dtype=np.float64)
        mean_r = arr.mean()
        if mean_r < 1.0:
            continue
        cv = float(arr.std() / mean_r)
        max_cv = max(max_cv, cv)

    return max_cv > FONT_SERIF_CV_THRESHOLD


def _horizontal_runs(zone: np.ndarray) -> List[int]:
    """统计二值图像中每行的前景连续 run 长度。"""
    runs: List[int] = []
    for row in zone:
        in_run = False
        length = 0
        for val in row:
            if val > 0:
                in_run = True
                length += 1
            elif in_run:
                if length > 0:
                    runs.append(length)
                in_run = False
                length = 0
        if in_run and length > 0:
            runs.append(length)
    return runs


# ── Italic 检测：轮廓角度 ──

def _detect_italic(
    binary: np.ndarray, font_size_est: float,
) -> tuple[bool, float]:
    """通过轮廓重心倾斜度判断是否斜体。

    对每个足够高的轮廓，计算顶部和底部像素的平均 X 偏移，
    由此得到倾斜角度。直立文字接近 0°，斜体通常 8-20°。
    """
    contours, _ = cv2.findContours(
        binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
    )

    min_h = font_size_est * 0.4
    angles: List[float] = []

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if h < min_h or w < 3:
            continue

        # 取轮廓内顶部 25% 和底部 25% 像素的平均 x
        pts = cnt.reshape(-1, 2)
        top_quarter = pts[pts[:, 1] < y + h * 0.25]
        bot_quarter = pts[pts[:, 1] > y + h * 0.75]

        if len(top_quarter) < 2 or len(bot_quarter) < 2:
            continue

        top_x = float(np.mean(top_quarter[:, 0]))
        bot_x = float(np.mean(bot_quarter[:, 0]))

        dx = top_x - bot_x
        dy = h * 0.5  # distance between center of top quarter and center of bottom quarter

        import math
        angle = abs(math.degrees(math.atan2(dx, dy)))
        angles.append(angle)

    if len(angles) < 3:
        return False, 0.0

    median_angle = float(np.median(angles))
    is_italic = FONT_ITALIC_THRESHOLD <= median_angle <= 25.0

    return is_italic, median_angle
