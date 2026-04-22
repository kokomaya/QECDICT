"""OpenAI 兼容翻译实现 — 调用 OpenAI-compatible API 批量翻译。

职责单一：只负责组装 API 请求并返回 TranslatedBlock 列表，
Prompt 构建和响应解析委托给 prompt_templates 模块。
支持流式翻译 (translate_stream) 和批量翻译 (translate)。
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Iterator, List, Optional

import httpx
import openai

from magic_mirror.interfaces.types import TextBlock, TranslatedBlock
from magic_mirror.translation.prompt_templates import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_stream_items,
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

    def translate_stream(self, blocks: List[TextBlock]) -> Iterator[TranslatedBlock]:
        """流式翻译：逐条 yield TranslatedBlock。

        通过 streaming API 接收文本，增量解析 JSON 对象，
        每解析出一条翻译即 yield。适用于渐进渲染场景。
        流结束后补发漏掉的项。失败时回退为原文。
        """
        if not blocks:
            return

        numbered_texts = [(i + 1, block.text) for i, block in enumerate(blocks)]
        user_prompt = build_user_prompt(numbered_texts)

        yielded_indices: set = set()
        try:
            for tb in self._stream_api(blocks, user_prompt):
                idx = next((i for i, b in enumerate(blocks) if b is tb.source), None)
                if idx is not None:
                    yielded_indices.add(idx)
                yield tb
        except Exception as exc:
            logger.error("流式翻译失败，回退未翻译的块: %s", exc)
            for i, block in enumerate(blocks):
                if i not in yielded_indices:
                    yield TranslatedBlock(source=block, translated_text=block.text)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _call_api(self, user_prompt: str) -> Dict[int, str]:
        """发送请求并解析响应，返回 {id: zh} 映射。"""
        t_api0 = time.perf_counter()
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
        t_api1 = time.perf_counter()
        logger.info("  翻译 API 响应  %.0fms", (t_api1 - t_api0) * 1000)

        mapping = parse_translation_response(content)
        if not mapping:
            logger.warning("翻译响应解析为空，原始内容: %s", content[:200])
        return mapping

    @staticmethod
    def _collect_stream(response) -> str:
        """从 streaming 响应中收集完整内容。"""
        chunks: List[str] = []
        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                chunks.append(delta.content)
        return "".join(chunks)

    def _stream_api(
        self,
        blocks: List[TextBlock],
        user_prompt: str,
    ) -> Iterator[TranslatedBlock]:
        """增量解析 streaming 响应，逐条 yield TranslatedBlock。"""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )

        t_stream0 = time.perf_counter()
        t_first_token = None
        accumulated = ""
        yielded_ids: set = set()

        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if not delta.content:
                continue
            if t_first_token is None:
                t_first_token = time.perf_counter()
                logger.info("  流式首 token  %.0fms",
                             (t_first_token - t_stream0) * 1000)
            accumulated += delta.content

            # 增量解析已完成的 JSON 对象
            items = parse_stream_items(accumulated)
            for item_id, zh in items.items():
                if item_id in yielded_ids:
                    continue
                yielded_ids.add(item_id)
                idx = item_id - 1
                if 0 <= idx < len(blocks):
                    yield TranslatedBlock(
                        source=blocks[idx], translated_text=zh,
                    )

        # 流结束后最终解析，补发漏掉的项
        final = parse_translation_response(accumulated)
        logger.debug("流式累积原文: %s", accumulated[:500])
        logger.debug("流式已 yield IDs: %s, 最终解析 IDs: %s",
                     sorted(yielded_ids), sorted(final.keys()))
        for item_id, zh in final.items():
            if item_id in yielded_ids:
                continue
            yielded_ids.add(item_id)
            idx = item_id - 1
            if 0 <= idx < len(blocks):
                yield TranslatedBlock(
                    source=blocks[idx], translated_text=zh,
                )

        t_stream1 = time.perf_counter()
        logger.info("  流式翻译完成  %.0fms  %d 条",
                     (t_stream1 - t_stream0) * 1000, len(yielded_ids))

        # 未翻译的块回退为原文
        for i, block in enumerate(blocks):
            if (i + 1) not in yielded_ids:
                logger.warning("块 #%d 未翻译，回退原文: %s",
                               i + 1, block.text[:80])
                yield TranslatedBlock(source=block, translated_text=block.text)

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