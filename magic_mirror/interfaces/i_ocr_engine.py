"""OCR 识别协议"""

from __future__ import annotations

from typing import List, Protocol

import numpy as np

from .types import TextBlock


class IOcrEngine(Protocol):
    """从图像中提取带位置信息的文本块"""

    def recognize(self, image: np.ndarray) -> List[TextBlock]:
        ...
