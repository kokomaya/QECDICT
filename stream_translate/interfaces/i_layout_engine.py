"""排版协议"""

from __future__ import annotations

from typing import List, Protocol, Tuple

import numpy as np

from .types import RenderBlock, TranslatedBlock


class ILayoutEngine(Protocol):
    """将翻译结果映射为可渲染块"""

    def compute_layout(
        self,
        blocks: List[TranslatedBlock],
        screenshot: np.ndarray,
        screen_bbox: Tuple[int, int, int, int],
    ) -> List[RenderBlock]:
        ...
