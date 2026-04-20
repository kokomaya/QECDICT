"""颜色采样器 — 从截图中提取文本块的背景色和前景色。

职责单一：只负责颜色采样，不涉及布局计算或文本渲染。
背景色：外围环形区域 + 中值模糊 + 量化众数。
前景色：Otsu 文字掩码 + K-Means 聚类，选与背景差异最大的簇。

改进策略：
  - 使用 Otsu 阈值生成文字掩码，隔离文字像素后再聚类
  - 增加 K-Means 迭代次数和聚类数，提高颜色精度
  - 加权采样：优先取文字掩码内的像素
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

    # 双边滤波：边缘保持 + 降噪
    blurred = cv2.bilateralFilter(region, 9, 75, 75)

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

    策略（优先级从高到低）：
      1. Otsu 阈值分离文字掩码 → 只对文字像素做 K-Means
      2. K-Means (k=3) 全区域像素聚类 → 选与背景差距最大的簇
      3. 亮度回退：亮背景 → 黑字，暗背景 → 白字

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

    # 尝试 Otsu 掩码隔离文字像素后精准采色
    try:
        text_bgr = _otsu_masked_color(region, bg_color)
        if text_bgr is not None:
            return (int(text_bgr[2]), int(text_bgr[1]), int(text_bgr[0]))
    except Exception:
        logger.debug("Otsu 掩码采色失败，降级到 K-Means 全区域")

    # 降级到全区域 K-Means
    pixels = region.reshape(-1, 3)
    if len(pixels) < _MIN_PIXELS_FOR_KMEANS:
        return _fallback_text_color(bg_color)

    try:
        text_bgr = _kmeans_text_color(pixels, bg_color)
        if text_bgr is None:
            return _fallback_text_color(bg_color)
        return (int(text_bgr[2]), int(text_bgr[1]), int(text_bgr[0]))
    except Exception:
        logger.debug("K-Means 聚类失败，回退到亮度策略")
        return _fallback_text_color(bg_color)


# ------------------------------------------------------------------
# 内部辅助
# ------------------------------------------------------------------

def _otsu_masked_color(
    region: np.ndarray,
    bg_color: Tuple[int, int, int, int],
) -> np.ndarray | None:
    """Otsu 阈值分离文字掩码，从文字像素中提取颜色。

    1. 灰度化 → Otsu 自动阈值 → 文字掩码
    2. 判断文字是深色还是浅色（与背景色比较）
    3. 对掩码内的文字像素取中值作为前景色

    Returns:
        BGR 颜色数组，或 None（像素不足时）。
    """
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 判断文字是黑底白字还是白底黑字
    bg_lum = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
    # 如果背景亮 → 文字暗 → 文字在 binary==0 的区域
    # 如果背景暗 → 文字亮 → 文字在 binary==255 的区域
    if bg_lum > 128:
        text_mask = (binary == 0)
    else:
        text_mask = (binary == 255)

    text_pixels = region[text_mask]
    if len(text_pixels) < _MIN_PIXELS_FOR_KMEANS:
        return None

    # 对文字像素做 K-Means (k=2) 取主色
    data = text_pixels.astype(np.float32)
    criteria = (
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER,
        50, 0.1,
    )
    _, labels, centers = cv2.kmeans(
        data, min(2, len(data)), None, criteria, 10, cv2.KMEANS_PP_CENTERS,
    )

    # 选像素最多的簇作为文字颜色
    counts = np.bincount(labels.flatten(), minlength=len(centers))
    dominant_idx = int(np.argmax(counts))
    return centers[dominant_idx]


def _kmeans_text_color(
    pixels: np.ndarray,
    bg_color: Tuple[int, int, int, int],
) -> np.ndarray | None:
    """K-Means (k=3) 聚类，返回与背景差异最大的簇中心 (BGR)。

    使用 k=3 比 k=2 更能区分背景、文字和过渡色。
    增加迭代次数和尝试次数以提高收敛精度。
    """
    data = pixels.astype(np.float32)
    k = min(3, len(data))
    criteria = (
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER,
        50,
        0.1,
    )
    _, labels, centers = cv2.kmeans(
        data, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS,
    )

    # bg_color 是 (R, G, B, A)，转为 BGR 用于距离计算
    bg_bgr = np.array([bg_color[2], bg_color[1], bg_color[0]], dtype=np.float32)

    # 选择与背景色 LAB 感知距离最大的簇
    best_center = None
    best_dist = -1.0
    for center in centers:
        dist = _lab_distance(center, bg_bgr)
        if dist > best_dist:
            best_dist = dist
            best_center = center

    if best_dist < 30:
        return None

    return best_center


def _lab_distance(bgr1: np.ndarray, bgr2: np.ndarray) -> float:
    """CIE LAB 空间的感知色差。"""
    p1 = np.array([[bgr1.astype(np.uint8)]], dtype=np.uint8)
    p2 = np.array([[bgr2.astype(np.uint8)]], dtype=np.uint8)
    lab1 = cv2.cvtColor(p1, cv2.COLOR_BGR2LAB)[0][0].astype(np.float32)
    lab2 = cv2.cvtColor(p2, cv2.COLOR_BGR2LAB)[0][0].astype(np.float32)
    return float(np.linalg.norm(lab1 - lab2))


def _fallback_text_color(
    bg_color: Tuple[int, int, int, int],
) -> Tuple[int, int, int]:
    """亮度策略回退：亮背景 → 黑字，暗背景 → 白字。"""
    luminance = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
    return (0, 0, 0) if luminance > 128 else (255, 255, 255)


def _pixel_mode(pixels: np.ndarray) -> Tuple[int, int, int]:
    """取像素数组中出现最多的颜色 (BGR)。

    将 BGR 量化到 16 级（减少噪声影响同时保留颜色精度），
    再取该簇的中值作为最终颜色。
    """
    # 量化：右移 4 位 (256 → 16 级)，比 8 级更精确
    quantized = (pixels >> 4).astype(np.uint32)
    # 编码为单值用于 bincount
    codes = (quantized[:, 0] << 8) | (quantized[:, 1] << 4) | quantized[:, 2]
    mode_code = np.argmax(np.bincount(codes))

    # 找到属于众数簇的原始像素
    mask = codes == mode_code
    cluster = pixels[mask]

    # 取中值作为代表色
    b = int(np.median(cluster[:, 0]))
    g = int(np.median(cluster[:, 1]))
    r = int(np.median(cluster[:, 2]))
    return (b, g, r)