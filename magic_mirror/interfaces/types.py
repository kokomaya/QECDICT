"""共享数据模型 — 所有模块间传递的 DTO"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

import numpy as np


class TextAlignment(Enum):
    """文本对齐方式"""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@dataclass
class TextBlock:
    """OCR 识别出的单个文本块"""

    text: str                                        # 识别的文本
    bbox: List[List[float]]                          # 四角坐标 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    font_size_est: float                             # 估算字号 (基于 bbox 高度)
    confidence: float                                # OCR 置信度


@dataclass
class TranslatedBlock:
    """翻译后的文本块 = TextBlock + 译文"""

    source: TextBlock
    translated_text: str                             # 翻译后的文本


@dataclass
class RenderBlock:
    """可渲染的文本块 = 屏幕坐标 + 渲染参数"""

    screen_x: int
    screen_y: int
    width: int
    height: int
    translated_text: str
    font_size: int
    bg_color: Tuple[int, int, int, int]              # RGBA
    text_color: Tuple[int, int, int]                 # RGB
    alignment: TextAlignment = TextAlignment.LEFT     # 文本对齐方式
    source_text: str = ""                             # OCR 原文（用于对照预览）


@dataclass
class CaptureResult:
    """截图结果"""

    image: np.ndarray                                # BGR 格式图像
    screen_bbox: Tuple[int, int, int, int]           # (x, y, w, h) 屏幕绝对坐标
