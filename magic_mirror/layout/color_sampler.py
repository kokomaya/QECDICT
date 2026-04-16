"""颜色采样器 — 从截图中提取文本块的背景色和前景色。

职责单一：只负责颜色采样，不涉及布局计算或文本渲染。
"""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

# 背景采样向外扩展像素数
_EXPAND_PX = 4


def sample_background_color(
    image: np.ndarray,
    bbox: List[List[float]],
) -> Tuple[int, int, int, int]:
    """从 bbox 外围区域采样背景色。

    Args:
        image: BGR 格式截图 (H, W, 3)。
        bbox: 四角坐标 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]。

    Returns:
        (R, G, B, A)，A 固定 255。
    """
    h, w = image.shape[:2]

    # 将四角坐标转为轴对齐矩形，clip 到图像范围内
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

    # 内部区域（用于排除）
    ix1 = max(x_min, ox1)
    iy1 = max(y_min, oy1)
    ix2 = min(x_max, ox2)
    iy2 = min(y_max, oy2)

    # 创建外围 mask：外围区域 = 扩展矩形 - 内部矩形
    mask = np.zeros((oy2 - oy1, ox2 - ox1), dtype=np.uint8)
    mask[:, :] = 255
    # 在 mask 中扣除内部区域
    inner_y1 = iy1 - oy1
    inner_y2 = iy2 - oy1
    inner_x1 = ix1 - ox1
    inner_x2 = ix2 - ox1
    if inner_y2 > inner_y1 and inner_x2 > inner_x1:
        mask[inner_y1:inner_y2, inner_x1:inner_x2] = 0

    region = image[oy1:oy2, ox1:ox2]

    # 如果外围区域太小（mask 几乎无有效像素），回退到整个扩展区域
    if cv2.countNonZero(mask) < 4:
        mask[:, :] = 255

    # 中值模糊降噪
    blurred = cv2.medianBlur(region, 5)

    # 取 mask 区域像素的众数
    pixels = blurred[mask > 0]  # shape: (N, 3), BGR
    if len(pixels) == 0:
        return (128, 128, 128, 255)

    b, g, r = _pixel_mode(pixels)
    return (int(r), int(g), int(b), 255)


def sample_text_color(
    image: np.ndarray,
    bbox: List[List[float]],
    bg_color: Tuple[int, int, int, int],
) -> Tuple[int, int, int]:
    """根据背景色计算前景文字颜色。

    MVP 阶段使用简化策略：与背景色反色，确保对比度。

    Args:
        image: BGR 格式截图（当前未使用，保留接口以便后续升级为 K-Means）。
        bbox: 四角坐标（保留接口）。
        bg_color: 背景色 (R, G, B, A)。

    Returns:
        (R, G, B) 前景色。
    """
    bg_r, bg_g, bg_b = bg_color[0], bg_color[1], bg_color[2]

    # 计算亮度 (ITU-R BT.601)
    luminance = 0.299 * bg_r + 0.587 * bg_g + 0.114 * bg_b

    # 亮背景 → 深色文字；暗背景 → 浅色文字
    if luminance > 128:
        return (0, 0, 0)
    else:
        return (255, 255, 255)


def _pixel_mode(pixels: np.ndarray) -> Tuple[int, int, int]:
    """取像素数组中出现最多的颜色 (BGR)。

    将 RGB 量化到 8 级（减少噪声影响）后统计众数，
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