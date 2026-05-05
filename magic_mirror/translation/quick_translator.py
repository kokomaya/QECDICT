"""快速互译器 — 单文本流式翻译，自动检测中英方向。

职责单一：只负责语言方向检测和流式翻译，
不涉及 UI 渲染、剪贴板操作或配置加载。
"""

from __future__ import annotations

import logging
from typing import Iterator, Literal

import openai
import httpx

from magic_mirror.config import get_default_provider, load_env
from magic_mirror.translation.prompt_templates import (
    QUICK_TRANSLATE_SYSTEM_EN2ZH,
    QUICK_TRANSLATE_SYSTEM_ZH2EN,
)

logger = logging.getLogger(__name__)

# 单次翻译最大字符数（超出则截断）
MAX_INPUT_CHARS = 2000


def detect_direction(text: str) -> Literal["zh2en", "en2zh"]:
    """检测文本翻译方向。

    统计 CJK 字符占比：
    - CJK 占比 > 20% → 中→英
    - 否则 → 英→中

    阈值 20% 适应混排文本（如 "AI模型"）。
    """
    if not text:
        return "en2zh"
    cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return "zh2en" if cjk_count / len(text) > 0.2 else "en2zh"


class QuickTranslator:
    """单文本流式翻译，自动检测中英方向。

    通过 provider_factory 读取与 MagicMirror 相同的 LLM 配置，
    不引入额外的配置文件或依赖。
    """

    def __init__(self) -> None:
        load_env()
        cfg = get_default_provider()

        http_client = (
            httpx.Client(verify=False)
            if not cfg.get("ssl_verify", True)
            else None
        )

        self._client = openai.OpenAI(
            api_key=cfg.get("api_key", "unused") or "unused",
            base_url=cfg["base_url"],
            default_headers=cfg.get("headers") or {},
            timeout=cfg.get("timeout", 60),
            max_retries=cfg.get("max_retries", 2),
            http_client=http_client,
        )
        self._model = cfg["model"]
        logger.debug("QuickTranslator 初始化完成，model=%s", self._model)

    def translate_stream(self, text: str) -> Iterator[str]:
        """流式返回翻译 token 字符串，供 UI 逐字追加。

        Args:
            text: 待翻译的原文（中文或英文）。超出 MAX_INPUT_CHARS 部分截断。

        Yields:
            每个 token 的字符串片段。

        Raises:
            openai.OpenAIError: API 调用异常（由调用方捕获并通过信号上报）。
        """
        if len(text) > MAX_INPUT_CHARS:
            text = text[:MAX_INPUT_CHARS]
            logger.warning("输入文本超出 %d 字符，已截断", MAX_INPUT_CHARS)

        direction = detect_direction(text)
        system_prompt = (
            QUICK_TRANSLATE_SYSTEM_ZH2EN
            if direction == "zh2en"
            else QUICK_TRANSLATE_SYSTEM_EN2ZH
        )
        logger.debug("翻译方向: %s，文本长度: %d", direction, len(text))

        stream = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
