"""翻译协议"""

from __future__ import annotations

from typing import List, Protocol

from .types import TextBlock, TranslatedBlock


class ITranslator(Protocol):
    """将文本块批量翻译"""

    def translate(self, blocks: List[TextBlock]) -> List[TranslatedBlock]:
        ...
