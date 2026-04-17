"""排版引擎 — 将翻译结果映射为可渲染的 RenderBlock 列表。

职责单一：只负责坐标映射、字号计算、段落合并和颜色采样的编排，
颜色采样委托给 color_sampler，不涉及 UI 渲染。
"""

from __future__ import annotations

import logging
from typing import List, Tuple

import numpy as np
from PyQt6.QtCore import QRect, Qt
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

        # ── 第一轮：逐段计算字号、颜色等参数 ──
        para_data: List[dict] = []
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
            final_h = merged_h

            # ── 颜色采样（合并所有子块区域） ──
            all_bboxes = [b.source.bbox for b in para]
            bg_color = sample_background_color(screenshot, first_src.bbox)
            text_color = _sample_merged_text_color(
                screenshot, all_bboxes, bg_color,
            )

            # 合并原文（用于对照预览）
            merged_source = "\n".join(b.source.text for b in para)

            para_data.append(dict(
                sx=sx, sy=sy, final_w=final_w, final_h=final_h,
                merged_text=merged_text, font_size=font_size,
                bg_color=bg_color, text_color=text_color,
                alignment=alignment, merged_source=merged_source,
                avg_font_est=avg_font_est,
            ))

        # ── 第二轮：统一相近原始字号的段落组的字号 ──
        _unify_font_sizes(para_data)

        # ── 第三轮：组装 RenderBlock ──
        for d in para_data:
            results.append(RenderBlock(
                screen_x=d["sx"],
                screen_y=d["sy"],
                width=d["final_w"],
                height=d["final_h"],
                translated_text=d["merged_text"],
                font_size=d["font_size"],
                bg_color=d["bg_color"],
                text_color=d["text_color"],
                alignment=d["alignment"],
                source_text=d["merged_source"],
            ))

        return results


# ------------------------------------------------------------------
# 字号统一
# ------------------------------------------------------------------

# 原始字号差异在此范围内视为"同组"（像素）
_FONT_GROUP_TOLERANCE = 3.0


def _unify_font_sizes(para_data: List[dict]) -> None:
    """将原始字号相近的段落组统一为组内最小字号。

    同一页面中原本相同字体大小的文本行，OCR 估算的 font_size_est
    可能略有偏差，但翻译后中文长度不同导致 _fit_font_size 得到
    差异较大的字号（短译文保持大字号，长译文被缩小），视觉上不协调。

    策略：
      1. 按 avg_font_est 排序后贪心分组（相邻差 ≤ 容差 → 同组）
      2. 每组内取最小 font_size，统一赋给组内所有段落
    """
    if len(para_data) <= 1:
        return

    # 构建 (index, avg_font_est) 并按 avg_font_est 排序
    indexed = sorted(enumerate(para_data), key=lambda t: t[1]["avg_font_est"])

    groups: List[List[int]] = [[indexed[0][0]]]
    prev_est = indexed[0][1]["avg_font_est"]

    for idx, d in indexed[1:]:
        if abs(d["avg_font_est"] - prev_est) <= _FONT_GROUP_TOLERANCE:
            groups[-1].append(idx)
        else:
            groups.append([idx])
        prev_est = d["avg_font_est"]

    # 每组统一为组内最小 font_size
    for group in groups:
        if len(group) < 2:
            continue
        min_fs = min(para_data[i]["font_size"] for i in group)
        for i in group:
            para_data[i]["font_size"] = min_fs


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
    # 字号差异检查：标题与正文不合并
    max_fs = max(a.source.font_size_est, b.source.font_size_est)
    if max_fs > 0:
        ratio = abs(a.source.font_size_est - b.source.font_size_est) / max_fs
        if ratio > 0.25:
            return False

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

    使用 QFontMetrics.boundingRect + TextWordWrap 精确测量
    自动换行后的文本尺寸，支持段落级长文本的重流。

    Args:
        text: 待渲染文本（可能含 \\n）。
        font_size_est: OCR 估算的原始字号。
        bbox_width: bbox 像素宽度。
        bbox_height: bbox 像素高度。
        n_lines: 文本行数（参考，实际以测量为准）。

    Returns:
        (final_font_size, max_line_render_width)
    """
    # pixelSize 的 fm.height() > pixelSize（含 descent），所以上界需放大
    base_size = max(int(font_size_est * FONT_SIZE_SCALE * 1.4), 8)
    min_size = max(int(font_size_est * FONT_SIZE_SCALE * MAX_FONT_SHRINK_RATIO), 8)

    def _fits(size: int) -> Tuple[bool, int]:
        """检查字号是否在 bbox 内不溢出（支持自动换行）。"""
        font = QFont(FONT_FAMILY_ZH)
        font.setPixelSize(size)
        fm = QFontMetrics(font)
        br = fm.boundingRect(
            QRect(0, 0, bbox_width, 100000),
            int(Qt.TextFlag.TextWordWrap),
            text,
        )
        fits = br.height() <= bbox_height if bbox_height > 0 else True
        return fits, br.width()

    # 先检查 base_size 是否已经不溢出
    ok, max_w = _fits(base_size)
    if ok:
        return base_size, max_w

    # 二分查找：lo 不溢出或可能溢出，hi 一定溢出
    lo, hi = min_size, base_size
    best_size = min_size
    _, best_w = _fits(min_size)

    while lo <= hi:
        mid = (lo + hi) // 2
        ok, w = _fits(mid)
        if ok:
            best_size = mid
            best_w = w
            lo = mid + 1
        else:
            hi = mid - 1

    return best_size, best_w


# ------------------------------------------------------------------
# 颜色采样辅助
# ------------------------------------------------------------------

def _sample_merged_text_color(
    screenshot: np.ndarray,
    bboxes: List[list],
    bg_color: Tuple[int, int, int, int],
) -> Tuple[int, int, int]:
    """从段落内所有子块的 bbox 采样前景色，取与背景差异最大的颜色。

    逐块调用 sample_text_color，选与 bg_color 欧氏距离最远者。
    """
    best_color: Tuple[int, int, int] = (0, 0, 0)
    best_dist = -1.0

    for bbox in bboxes:
        tc = sample_text_color(screenshot, bbox, bg_color)
        dist = (
            (tc[0] - bg_color[0]) ** 2
            + (tc[1] - bg_color[1]) ** 2
            + (tc[2] - bg_color[2]) ** 2
        ) ** 0.5
        if dist > best_dist:
            best_dist = dist
            best_color = tc

    return best_color