"""颜色采样器 — 从截图中提取文本块的背景色和前景色。

职责单一：只负责颜色采样，不涉及布局计算或文本渲染。
背景色：外围环形区域 + 中值模糊 + 量化众数。
前景色：K-Means (k=2) 聚类，选与背景差异最大的簇。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 背景采样向外扩展像素数（5-10px 范围，排除文字像素干扰）
_EXPAND_PX = 8

# K-Means 所需的最小像素数，不足时回退到亮度策略
_MIN_PIXELS_FOR_KMEANS = 20


# ------------------------------------------------------------------
# 背景色采样
# ------------------------------------------------------------------

def sample_background_color(
    image: np.ndarray,
    bbox: List[List[float]],
) -> Tuple[int, int, int, int]:
    """从 bbox 外围环形区域采样背景色。

    策略：bbox 外围 8px 环形区域 → 中值模糊降噪 → 量化众数提取。
    排除文字像素干扰，只采样背景区域。

    Args:
        image: BGR 格式截图 (H, W, 3)。
        bbox: 四角坐标 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]。

    Returns:
        (R, G, B, A)，A 固定 255。
    """
    h, w = image.shape[:2]

    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    x_min = max(int(min(xs)), 0)
    x_max = min(int(max(xs)), w)
    y_min = max(int(min(ys)), 0)
    y_max = min(int(max(ys)), h)

    # bbox 退化（宽或高为 0 或负）→ 返回灰色默认值
    if x_max <= x_min or y_max <= y_min:
        return (128, 128, 128, 255)

    # 向外扩展取样，clip 到图像边界
    ox1 = max(x_min - _EXPAND_PX, 0)
    oy1 = max(y_min - _EXPAND_PX, 0)
    ox2 = min(x_max + _EXPAND_PX, w)
    oy2 = min(y_max + _EXPAND_PX, h)

    # 扩展区域退化检查
    if ox2 <= ox1 or oy2 <= oy1:
        return (128, 128, 128, 255)

    # 构建外围 mask：扩展矩形 − 内部矩形 = 只含背景的环
    mask = np.ones((oy2 - oy1, ox2 - ox1), dtype=np.uint8) * 255
    inner_y1 = max(y_min - oy1, 0)
    inner_y2 = min(y_max - oy1, oy2 - oy1)
    inner_x1 = max(x_min - ox1, 0)
    inner_x2 = min(x_max - ox1, ox2 - ox1)
    if inner_y2 > inner_y1 and inner_x2 > inner_x1:
        mask[inner_y1:inner_y2, inner_x1:inner_x2] = 0

    region = image[oy1:oy2, ox1:ox2]

    # 外围像素不足时回退到整个扩展区域
    if cv2.countNonZero(mask) < 4:
        mask[:, :] = 255

    # 中值模糊降噪
    blurred = cv2.medianBlur(region, 5)

    pixels = blurred[mask > 0]  # shape: (N, 3), BGR
    if len(pixels) == 0:
        return (128, 128, 128, 255)

    b, g, r = _pixel_mode(pixels)
    return (int(r), int(g), int(b), 255)


# ------------------------------------------------------------------
# 前景色采样
# ------------------------------------------------------------------

def sample_text_color(
    image: np.ndarray,
    bbox: List[List[float]],
    bg_color: Tuple[int, int, int, int],
) -> Tuple[int, int, int]:
    """从 bbox 内部区域提取前景文字颜色。

    策略：K-Means (k=2) 聚类 bbox 内部像素，
    选择与背景色欧氏距离最大的簇中心作为文字颜色。
    支持彩色文字（链接蓝色、错误红色等）。

    当内部像素不足或聚类失败时，回退到亮度策略。

    Args:
        image: BGR 格式截图 (H, W, 3)。
        bbox: 四角坐标 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]。
        bg_color: 背景色 (R, G, B, A)。

    Returns:
        (R, G, B) 前景色。
    """
    h, w = image.shape[:2]

    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    x_min = max(int(min(xs)), 0)
    x_max = min(int(max(xs)), w)
    y_min = max(int(min(ys)), 0)
    y_max = min(int(max(ys)), h)

    if x_max <= x_min or y_max <= y_min:
        return _fallback_text_color(bg_color)

    region = image[y_min:y_max, x_min:x_max]
    pixels = region.reshape(-1, 3)  # (N, 3) BGR

    if len(pixels) < _MIN_PIXELS_FOR_KMEANS:
        return _fallback_text_color(bg_color)

    try:
        text_bgr = _kmeans_text_color(pixels, bg_color)
        if text_bgr is None:
            return _fallback_text_color(bg_color)
        return (int(text_bgr[2]), int(text_bgr[1]), int(text_bgr[0]))  # BGR → RGB
    except Exception:
        logger.debug("K-Means 聚类失败，回退到亮度策略")
        return _fallback_text_color(bg_color)


# ------------------------------------------------------------------
# 内部辅助
# ------------------------------------------------------------------

def _kmeans_text_color(
    pixels: np.ndarray,
    bg_color: Tuple[int, int, int, int],
) -> np.ndarray | None:
    """K-Means (k=2) 聚类，返回与背景差异最大的簇中心 (BGR)。

    两个簇中心都太接近背景色时返回 None。
    """
    data = pixels.astype(np.float32)
    criteria = (
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER,
        10,    # max iterations
        1.0,   # epsilon
    )
    _, labels, centers = cv2.kmeans(
        data, 2, None, criteria, 3, cv2.KMEANS_PP_CENTERS,
    )

    # bg_color 是 (R, G, B, A)，转为 BGR 用于距离计算
    bg_bgr = np.array([bg_color[2], bg_color[1], bg_color[0]], dtype=np.float32)

    # 选择与背景色欧氏距离最大的簇
    dist0 = float(np.linalg.norm(centers[0] - bg_bgr))
    dist1 = float(np.linalg.norm(centers[1] - bg_bgr))

    best_dist = max(dist0, dist1)
    # 两个簇都太接近背景 → 无法区分前景，返回 None 触发回退
    if best_dist < 30:
        return None

    return centers[0] if dist0 > dist1 else centers[1]


def _fallback_text_color(
    bg_color: Tuple[int, int, int, int],
) -> Tuple[int, int, int]:
    """亮度策略回退：亮背景 → 黑字，暗背景 → 白字。"""
    luminance = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
    return (0, 0, 0) if luminance > 128 else (255, 255, 255)


def _pixel_mode(pixels: np.ndarray) -> Tuple[int, int, int]:
    """取像素数组中出现最多的颜色 (BGR)。

    将 BGR 量化到 8 级（减少噪声影响）后统计众数，
    再取该簇的中值作为最终颜色。
    """
    # 量化：右移 5 位 (256 → 8 级)
    quantized = (pixels >> 5).astype(np.uint32)
    # 编码为单值用于 bincount
    codes = (quantized[:, 0] << 6) | (quantized[:, 1] << 3) | quantized[:, 2]
    mode_code = np.argmax(np.bincount(codes))

    # 找到属于众数簇的原始像素
    mask = codes == mode_code
    cluster = pixels[mask]

    # 取中值作为代表色
    b = int(np.median(cluster[:, 0]))
    g = int(np.median(cluster[:, 1]))
    r = int(np.median(cluster[:, 2]))
    return (b, g, r)