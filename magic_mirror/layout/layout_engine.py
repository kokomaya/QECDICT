"""排版引擎 — 将翻译结果映射为可渲染的 RenderBlock 列表。

职责单一：只负责坐标映射、字号计算、段落合并和颜色采样的编排，
颜色采样委托给 color_sampler，不涉及 UI 渲染。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import numpy as np
from PyQt6.QtGui import QFont, QFontMetrics

from magic_mirror.config.settings import (
    FONT_FAMILY_ZH,
    FONT_SIZE_SCALE,
    MAX_FONT_SHRINK_RATIO,
)
from magic_mirror.interfaces.types import RenderBlock, TextAlignment, TranslatedBlock
from magic_mirror.layout.color_sampler import sample_background_color, sample_text_color

logger = logging.getLogger(__name__)

# 当文字缩小到下限仍溢出时，允许宽度扩展的最大比例
_MAX_WIDTH_EXPAND = 1.3

# 相邻文本块 Y 间距低于此比例（相对行高）时合并为段落
_MERGE_Y_GAP_RATIO = 0.8


class DefaultLayoutEngine:
    """ILayoutEngine 实现 — 将 TranslatedBlock 列表映射为 RenderBlock 列表。"""

    def compute_layout(
        self,
        blocks: List[TranslatedBlock],
        screenshot: np.ndarray,
        screen_bbox: Tuple[int, int, int, int],
    ) -> List[RenderBlock]:
        """计算每个翻译块的屏幕渲染参数。

        先合并相邻行为段落，再逐段计算字号和颜色。

        Args:
            blocks: 翻译后的文本块列表。
            screenshot: BGR 格式截图。
            screen_bbox: 截图对应的屏幕区域 (x, y, w, h)。

        Returns:
            可渲染的 RenderBlock 列表。
        """
        if not blocks:
            return []

        # 合并相邻行为段落
        paragraphs = _merge_adjacent_blocks(blocks)

        # 检测段落对齐方式
        para_alignments = _detect_alignments(paragraphs, screen_bbox[2])

        screen_x0, screen_y0 = screen_bbox[0], screen_bbox[1]
        results: List[RenderBlock] = []

        for para, alignment in zip(paragraphs, para_alignments):
            first_src = para[0].source

            # ── 段落包围框：合并所有子块的 bbox ──
            merged_left, merged_top, merged_w, merged_h = _merged_bbox(
                [b.source.bbox for b in para],
            )
            sx = screen_x0 + merged_left
            sy = screen_y0 + merged_top

            # 合并译文（多行用 \n 连接）
            merged_text = "\n".join(b.translated_text for b in para)

            # ── 字号计算（二分查找最优字号） ──
            avg_font_est = sum(b.source.font_size_est for b in para) / len(para)
            n_lines = len(para)
            font_size, render_w = _fit_font_size(
                merged_text, avg_font_est, merged_w, merged_h, n_lines,
            )

            final_w = max(merged_w, min(render_w, int(merged_w * _MAX_WIDTH_EXPAND)))

            # ── 颜色采样（用第一个块的 bbox 采样） ──
            bg_color = sample_background_color(screenshot, first_src.bbox)
            text_color = sample_text_color(screenshot, first_src.bbox, bg_color)

            results.append(RenderBlock(
                screen_x=sx,
                screen_y=sy,
                width=final_w,
                height=merged_h,
                translated_text=merged_text,
                font_size=font_size,
                bg_color=bg_color,
                text_color=text_color,
                alignment=alignment,
            ))

        return results


# ------------------------------------------------------------------
# 段落合并
# ------------------------------------------------------------------

def _merge_adjacent_blocks(
    blocks: List[TranslatedBlock],
) -> List[List[TranslatedBlock]]:
    """将 Y 坐标相邻、X 范围重叠的文本块合并为段落。

    判定条件：
      1. 两块的 Y 间距 < 前一块行高 × _MERGE_Y_GAP_RATIO
      2. 两块的 X 范围有重叠（水平交集 > 0）

    Args:
        blocks: 按 Y 坐标排序的翻译块列表。

    Returns:
        段落列表，每个段落是一组应合并渲染的 TranslatedBlock。
    """
    if not blocks:
        return []

    # 按 bbox 顶部 Y 坐标排序
    sorted_blocks = sorted(blocks, key=lambda b: min(pt[1] for pt in b.source.bbox))
    paragraphs: List[List[TranslatedBlock]] = [[sorted_blocks[0]]]

    for blk in sorted_blocks[1:]:
        prev = paragraphs[-1][-1]
        if _should_merge(prev, blk):
            paragraphs[-1].append(blk)
        else:
            paragraphs.append([blk])

    return paragraphs


def _should_merge(a: TranslatedBlock, b: TranslatedBlock) -> bool:
    """判断两个相邻文本块是否应合并为同一段落。"""
    a_left, a_top, a_w, a_h = _bbox_rect(a.source.bbox)
    b_left, b_top, b_w, b_h = _bbox_rect(b.source.bbox)

    # Y 间距：b 的顶部 − a 的底部
    y_gap = b_top - (a_top + a_h)
    if y_gap > a_h * _MERGE_Y_GAP_RATIO:
        return False

    # X 范围重叠检查
    a_right = a_left + a_w
    b_right = b_left + b_w
    overlap = min(a_right, b_right) - max(a_left, b_left)
    return overlap > 0


# ------------------------------------------------------------------
# 对齐检测
# ------------------------------------------------------------------

def _detect_alignments(
    paragraphs: List[List[TranslatedBlock]],
    region_width: int,
) -> List[TextAlignment]:
    """分析各段落的 X 坐标分布，推断对齐方式。

    对每个段落内的所有文本块，统计 left / center_x / right 坐标，
    判断哪种对齐方式的离散程度最小。

    Args:
        paragraphs: 段落列表。
        region_width: 截图区域宽度（用于居中参考）。

    Returns:
        与段落列表等长的对齐方式列表。
    """
    results: List[TextAlignment] = []

    for para in paragraphs:
        if len(para) < 2:
            # 单行无法判断对齐，默认左对齐
            results.append(TextAlignment.LEFT)
            continue

        lefts: List[float] = []
        centers: List[float] = []
        rights: List[float] = []

        for blk in para:
            l, t, w, h = _bbox_rect(blk.source.bbox)
            lefts.append(l)
            centers.append(l + w / 2)
            rights.append(l + w)

        # 离散程度：标准差越小 → 对齐越好
        std_left = _std(lefts)
        std_center = _std(centers)
        std_right = _std(rights)

        min_std = min(std_left, std_center, std_right)
        if min_std == std_center:
            results.append(TextAlignment.CENTER)
        elif min_std == std_right:
            results.append(TextAlignment.RIGHT)
        else:
            results.append(TextAlignment.LEFT)

    return results


def _std(values: List[float]) -> float:
    """计算标准差（无 numpy 依赖的轻量版）。"""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / n) ** 0.5


# ------------------------------------------------------------------
# bbox 工具
# ------------------------------------------------------------------

def _bbox_rect(bbox: list) -> Tuple[int, int, int, int]:
    """四角坐标 → (left, top, width, height) 轴对齐矩形。"""
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    left = int(min(xs))
    top = int(min(ys))
    width = max(int(max(xs)) - left, 1)
    height = max(int(max(ys)) - top, 1)
    return left, top, width, height


def _merged_bbox(bboxes: list) -> Tuple[int, int, int, int]:
    """多个四角坐标 → 合并后的 (left, top, width, height)。"""
    all_xs = [pt[0] for bbox in bboxes for pt in bbox]
    all_ys = [pt[1] for bbox in bboxes for pt in bbox]
    left = int(min(all_xs))
    top = int(min(all_ys))
    width = max(int(max(all_xs)) - left, 1)
    height = max(int(max(all_ys)) - top, 1)
    return left, top, width, height


# ------------------------------------------------------------------
# 字号计算
# ------------------------------------------------------------------

def _fit_font_size(
    text: str,
    font_size_est: float,
    bbox_width: int,
    bbox_height: int,
    n_lines: int,
) -> Tuple[int, int]:
    """二分查找在 bbox 内不溢出的最大字号。

    在 [min_size, base_size] 区间二分，用 QFontMetrics 精确测量
    每行宽度，找到最大不溢出的字号。

    Args:
        text: 待渲染文本（可能含 \\n）。
        font_size_est: OCR 估算的原始字号。
        bbox_width: bbox 像素宽度。
        bbox_height: bbox 像素高度。
        n_lines: 文本行数。

    Returns:
        (final_font_size, max_line_render_width)
    """
    base_size = max(int(font_size_est * FONT_SIZE_SCALE), 8)
    min_size = max(int(base_size * MAX_FONT_SHRINK_RATIO), 8)

    lines = text.split("\n")

    # 先检查 base_size 是否已经不溢出
    max_w = _max_line_width(lines, base_size)
    if max_w <= bbox_width:
        return base_size, max_w

    # 二分查找：lo 不溢出或可能溢出，hi 一定溢出
    lo, hi = min_size, base_size
    best_size = min_size
    best_w = _max_line_width(lines, min_size)

    while lo <= hi:
        mid = (lo + hi) // 2
        w = _max_line_width(lines, mid)
        if w <= bbox_width:
            best_size = mid
            best_w = w
            lo = mid + 1
        else:
            hi = mid - 1

    return best_size, best_w


def _max_line_width(lines: list[str], font_size: int) -> int:
    """测量多行文本中最宽一行的渲染宽度。"""
    font = QFont(FONT_FAMILY_ZH, font_size)
    fm = QFontMetrics(font)
    return max(fm.horizontalAdvance(line) for line in lines)