"""OpenAI 兼容翻译实现 — 调用 OpenAI-compatible API 批量翻译。

职责单一：只负责组装 API 请求并返回 TranslatedBlock 列表，
Prompt 构建和响应解析委托给 prompt_templates 模块。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import httpx
import openai

from magic_mirror.interfaces.types import TextBlock, TranslatedBlock
from magic_mirror.translation.prompt_templates import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_translation_response,
)

logger = logging.getLogger(__name__)


class OpenAITranslator:
    """ITranslator 实现 — 通过 OpenAI 兼容 API 进行翻译。"""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 60,
        max_retries: int = 2,
        stream: bool = False,
        ssl_verify: bool = True,
    ) -> None:
        # 自签名证书场景：传入自定义 httpx 客户端禁用 SSL 验证
        http_client = httpx.Client(
            verify=ssl_verify,
        ) if not ssl_verify else None

        self._client = openai.OpenAI(
            api_key=api_key or "unused",
            base_url=base_url,
            default_headers=headers or {},
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )
        self._model = model
        self._timeout = timeout
        self._stream = stream

    def translate(self, blocks: List[TextBlock]) -> List[TranslatedBlock]:
        """批量翻译文本块。

        API 不可用时优雅降级：所有块的译文回退为原文。
        """
        if not blocks:
            return []

        numbered_texts = [(i + 1, block.text) for i, block in enumerate(blocks)]
        user_prompt = build_user_prompt(numbered_texts)

        try:
            mapping = self._call_api(user_prompt)
        except Exception as exc:
            logger.error("翻译 API 调用失败，回退为原文: %s", exc)
            return self._fallback(blocks)

        return self._build_results(blocks, numbered_texts, mapping)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _call_api(self, user_prompt: str) -> Dict[int, str]:
        """发送请求并解析响应，返回 {id: zh} 映射。"""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=self._stream,
        )

        if self._stream:
            content = self._collect_stream(response)
        else:
            content = response.choices[0].message.content or ""

        mapping = parse_translation_response(content)
        if not mapping:
            logger.warning("翻译响应解析为空，原始内容: %s", content[:200])
        return mapping

    @staticmethod
    def _collect_stream(response) -> str:
        """从 streaming 响应中收集完整内容。"""
        chunks: List[str] = []
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                chunks.append(delta.content)
        return "".join(chunks)

    @staticmethod
    def _build_results(
        blocks: List[TextBlock],
        numbered_texts: List[tuple],
        mapping: Dict[int, str],
    ) -> List[TranslatedBlock]:
        """按编号匹配翻译结果，未匹配的回退为原文。"""
        results: List[TranslatedBlock] = []
        for idx, block in enumerate(blocks):
            seq = idx + 1
            translated = mapping.get(seq, block.text)
            results.append(TranslatedBlock(source=block, translated_text=translated))
        return results

    @staticmethod
    def _fallback(blocks: List[TextBlock]) -> List[TranslatedBlock]:
        """全部回退为原文。"""
        return [
            TranslatedBlock(source=b, translated_text=b.text)
            for b in blocks
        ]