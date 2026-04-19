"""Connected Component 验证器 — 补漏被主检测器遗漏的文本区域。

通过连通分量分析找到图像中的前景区域，
与已检测的文本块比对，对未覆盖区域进行二次 OCR。
"""

from __future__ import annotations

import logging
from typing import Callable, List, Tuple

import cv2
import numpy as np

from magic_mirror.config.settings import (
    OCR_CC_VERIFY_ENABLED,
    OCR_CONFIDENCE_THRESHOLD,
    OCR_DET_BOX_THRESH_LOW,
)
from magic_mirror.interfaces.types import TextBlock

logger = logging.getLogger(__name__)

_CC_MIN_ASPECT = 0.1
_CC_MAX_ASPECT = 15.0
_CC_IOU_THRESHOLD = 0.3
_CC_CLUSTER_X_GAP_FACTOR = 2.0
_CC_CLUSTER_Y_TOLERANCE = 0.5
_CC_PAD = 3


def verify_completeness(
    image: np.ndarray,
    detected_blocks: List[TextBlock],
    run_ocr: Callable[[np.ndarray, float], list],
) -> List[TextBlock]:
    """用连通分量分析验证 OCR 完整性，补漏遗漏区域。

    Args:
        image: BGR 原图。
        detected_blocks: 已检测的文本块列表。
        run_ocr: OCR 回调 (crop, threshold) -> [(bbox, text, conf), ...]。

    Returns:
        合并后的文本块列表（原 + 补漏）。
    """
    if not OCR_CC_VERIFY_ENABLED or not detected_blocks:
        return detected_blocks

    h, w = image.shape[:2]

    median_h = float(np.median([b.font_size_est for b in detected_blocks]))
    if median_h < 5:
        return detected_blocks

    # Otsu 二值化 → 前景为白
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )

    # 前景占比检查：若前景过多说明可能反色，翻转
    fg_ratio = np.count_nonzero(binary) / binary.size
    if fg_ratio > 0.7:
        binary = cv2.bitwise_not(binary)

    # 连通分量分析
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8,
    )

    # 过滤分量（保守策略：只保留尺寸接近已检测文字的分量）
    min_h_cc = median_h * 0.5
    max_h_cc = median_h * 2.5
    min_area_cc = median_h * median_h * 0.1
    valid_ccs: List[Tuple[int, int, int, int, float]] = []

    for i in range(1, num_labels):  # 跳过背景
        cx, cy, cw, ch, area = stats[i]
        if ch < min_h_cc or ch > max_h_cc:
            continue
        if cw < 5 or area < min_area_cc:
            continue
        aspect = cw / ch if ch > 0 else 0
        if aspect < 0.2 or aspect > 10.0:
            continue
        cy_center = centroids[i][1]
        valid_ccs.append((cx, cy, cw, ch, cy_center))

    if not valid_ccs:
        return detected_blocks

    # 聚类：垂直中心接近 + 水平间距小 → 同一文本行
    clusters = _cluster_components(valid_ccs, median_h)

    # 构建已检测 bbox 列表
    existing_rects = [_bbox_to_rect(b.bbox) for b in detected_blocks]

    new_blocks: List[TextBlock] = []

    for cluster in clusters:
        # 至少 3 个分量才构成有意义的文本行候选
        if len(cluster) < 3:
            continue

        # 合并簇为候选 bbox
        all_x1 = min(c[0] for c in cluster) - _CC_PAD
        all_y1 = min(c[1] for c in cluster) - _CC_PAD
        all_x2 = max(c[0] + c[2] for c in cluster) + _CC_PAD
        all_y2 = max(c[1] + c[3] for c in cluster) + _CC_PAD
        all_x1 = max(all_x1, 0)
        all_y1 = max(all_y1, 0)
        all_x2 = min(all_x2, w)
        all_y2 = min(all_y2, h)

        cand_rect = (all_x1, all_y1, all_x2, all_y2)

        # 跳过已覆盖区域：IoU 或交集占比超阈值
        covered = False
        for er in existing_rects:
            if _iou(cand_rect, er) > 0.15:
                covered = True
                break
            # 候选区域大部分被已有 bbox 覆盖
            inter_area = _intersection_area(cand_rect, er)
            cand_area = (cand_rect[2] - cand_rect[0]) * (cand_rect[3] - cand_rect[1])
            if cand_area > 0 and inter_area / cand_area > 0.5:
                covered = True
                break
        if covered:
            continue

        # 裁剪并 OCR
        crop = image[all_y1:all_y2, all_x1:all_x2]
        if crop.size == 0:
            continue

        raw = run_ocr(crop, OCR_DET_BOX_THRESH_LOW)
        for bbox_pts, text, conf in raw:
            text = text.strip()
            if not text or conf < OCR_CONFIDENCE_THRESHOLD:
                continue
            # 坐标映射回原图
            mapped_bbox = [
                [pt[0] + all_x1, pt[1] + all_y1] for pt in bbox_pts
            ]
            font_est = _estimate_font_size(mapped_bbox)

            from magic_mirror.ocr.font_analyzer import analyze_font
            fi = analyze_font(image, mapped_bbox, font_est)

            new_blocks.append(TextBlock(
                text=text,
                bbox=mapped_bbox,
                font_size_est=font_est,
                confidence=conf,
                font_info=fi,
            ))

    if new_blocks:
        logger.debug("CC 验证补漏 %d 个文本块", len(new_blocks))

    return detected_blocks + new_blocks


def _cluster_components(
    ccs: List[Tuple[int, int, int, int, float]],
    median_h: float,
) -> List[List[Tuple[int, int, int, int, float]]]:
    """按垂直中心和水平间距聚类连通分量。"""
    # 按 y_center 排序
    sorted_ccs = sorted(ccs, key=lambda c: c[4])
    clusters: List[List[Tuple[int, int, int, int, float]]] = [[sorted_ccs[0]]]

    for cc in sorted_ccs[1:]:
        merged = False
        for cluster in clusters:
            # 检查 y_center 接近
            avg_y = sum(c[4] for c in cluster) / len(cluster)
            if abs(cc[4] - avg_y) > median_h * _CC_CLUSTER_Y_TOLERANCE:
                continue
            # 检查 x 间距
            cluster_x2 = max(c[0] + c[2] for c in cluster)
            cluster_x1 = min(c[0] for c in cluster)
            if cc[0] - cluster_x2 < median_h * _CC_CLUSTER_X_GAP_FACTOR and \
               cc[0] + cc[2] > cluster_x1:
                cluster.append(cc)
                merged = True
                break
        if not merged:
            clusters.append([cc])

    return clusters


def _bbox_to_rect(bbox: list) -> Tuple[int, int, int, int]:
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


def _iou(r1: Tuple, r2: Tuple) -> float:
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


def _intersection_area(r1: Tuple, r2: Tuple) -> float:
    x1 = max(r1[0], r2[0])
    y1 = max(r1[1], r2[1])
    x2 = min(r1[2], r2[2])
    y2 = min(r1[3], r2[3])
    return max(0, x2 - x1) * max(0, y2 - y1)


def _estimate_font_size(bbox: list) -> float:
    left_h = abs(bbox[3][1] - bbox[0][1])
    right_h = abs(bbox[2][1] - bbox[1][1])
    return (left_h + right_h) / 2.0
