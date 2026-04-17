"""聊天服务 — 管理多轮对话上下文与 LLM 调用。

职责单一：维护对话消息列表、估算 token 用量、调用 LLM 流式 API。
不涉及 UI 渲染或模型选择持久化。
"""

from __future__ import annotations

import logging
from typing import Iterator, List, Optional

import httpx
import openai

from magic_mirror.config import get_default_provider, load_env

logger = logging.getLogger(__name__)

# 上下文 token 预算（粗略估算，1 token ≈ 4 字符中文 / 4 字符英文）
_MAX_CONTEXT_CHARS = 24000       # ≈ 6000 token
_CHARS_PER_TOKEN = 4

_CHAT_SYSTEM_PROMPT = (
    "你是一个智能助手。用户会提供一段 OCR 提取的原文作为上下文，"
    "请基于该文本回答用户的问题。回答使用中文，简洁准确。"
)


class ChatSession:
    """单次聊天会话 — 管理消息历史和 token 预算。"""

    def __init__(self, context_text: str, model: str) -> None:
        self._model = model
        self._messages: List[dict] = [
            {"role": "system", "content": _CHAT_SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是 OCR 提取的原文，请基于此回答后续问题：\n\n{context_text}"},
            {"role": "assistant", "content": "好的，我已阅读以上文本。请问有什么问题？"},
        ]
        self._client: openai.OpenAI | None = None

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        self._model = value

    @property
    def messages(self) -> List[dict]:
        return list(self._messages)

    def send_stream(self, user_input: str) -> Iterator[str]:
        """发送用户消息并流式返回助手回复片段。

        自动管理上下文窗口：当消息总字符数超过预算时，
        裁剪早期对话轮次（保留 system + 原文 context + 最近轮次）。
        """
        self._messages.append({"role": "user", "content": user_input})
        self._trim_context()

        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=self._messages,
                stream=True,
            )

            collected = []
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    collected.append(delta.content)
                    yield delta.content

            assistant_text = "".join(collected)
            self._messages.append({"role": "assistant", "content": assistant_text})
        except Exception as exc:
            logger.error("聊天 API 调用失败: %s", exc)
            error_msg = f"[错误] API 调用失败: {exc}"
            self._messages.append({"role": "assistant", "content": error_msg})
            yield error_msg

    def clear_history(self) -> None:
        """清空对话历史，仅保留 system + 原文 context。"""
        self._messages = self._messages[:3]

    def estimate_tokens(self) -> int:
        """粗略估算当前消息列表的 token 数。"""
        total_chars = sum(len(m["content"]) for m in self._messages)
        return total_chars // _CHARS_PER_TOKEN

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_client(self) -> openai.OpenAI:
        """惰性创建 OpenAI 客户端。"""
        if self._client is not None:
            return self._client

        load_env()
        provider = get_default_provider()

        http_client = httpx.Client(
            verify=provider.get("ssl_verify", True),
        ) if not provider.get("ssl_verify", True) else None

        self._client = openai.OpenAI(
            api_key=provider.get("api_key", "unused"),
            base_url=provider["base_url"],
            default_headers=provider.get("headers", {}),
            timeout=provider.get("timeout", 60),
            max_retries=provider.get("max_retries", 2),
            http_client=http_client,
        )
        return self._client

    def _trim_context(self) -> None:
        """当消息总字符超过预算时，裁剪中间的对话轮次。

        保留策略：system(0) + context(1) + ack(2) + ... + 最近 N 轮。
        从第 3 条开始删除最早的对话对，直到低于预算。
        """
        total = sum(len(m["content"]) for m in self._messages)
        while total > _MAX_CONTEXT_CHARS and len(self._messages) > 4:
            # 删除第 3 条（最早的用户对话），保留前 3 条固定上下文
            removed = self._messages.pop(3)
            total -= len(removed["content"])
            logger.debug("裁剪上下文：移除 %s (len=%d)，剩余 %d 条",
                         removed["role"], len(removed["content"]), len(self._messages))
