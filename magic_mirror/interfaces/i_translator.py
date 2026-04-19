"""翻译协议"""

from __future__ import annotations

from typing import Iterator, List, Protocol

from .types import TextBlock, TranslatedBlock


class ITranslator(Protocol):
    """将文本块批量翻译"""

    def translate(self, blocks: List[TextBlock]) -> List[TranslatedBlock]:
        ...

    def translate_stream(self, blocks: List[TextBlock]) -> Iterator[TranslatedBlock]:
        """逐条翻译并流式返回，用于渐进渲染。

        默认行为可回退到 translate() 一次性返回。
        """
        ...
