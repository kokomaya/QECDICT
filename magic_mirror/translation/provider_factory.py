"""翻译后端工厂 — 根据配置创建 ITranslator 实例。

职责单一：只负责根据配置字典分发创建对应的 Translator，
不涉及配置文件读取、Prompt 管理或翻译逻辑。
"""

from __future__ import annotations

from magic_mirror.config import get_default_provider, load_env
from magic_mirror.interfaces import ITranslator

_SUPPORTED_TYPES = ("openai_compatible",)


def create_translator(provider_config: dict) -> ITranslator:
    """根据 provider 配置字典创建 ITranslator 实例。

    Args:
        provider_config: 单个 provider 的配置，至少包含 ``type`` 字段。
            ``openai_compatible`` 类型还需 base_url, model 等字段。

    Returns:
        实现了 ITranslator 协议的翻译实例。

    Raises:
        ValueError: ``type`` 字段缺失或不被支持。
    """
    backend_type = provider_config.get("type")

    if not backend_type:
        raise ValueError(
            "provider 配置中缺少 'type' 字段。"
            f" 支持的类型: {list(_SUPPORTED_TYPES)}"
        )

    if backend_type == "openai_compatible":
        from magic_mirror.translation.openai_translator import OpenAITranslator

        return OpenAITranslator(
            base_url=provider_config["base_url"],
            model=provider_config["model"],
            api_key=provider_config.get("api_key", ""),
            headers=provider_config.get("headers"),
            timeout=provider_config.get("timeout", 60),
            max_retries=provider_config.get("max_retries", 2),
            stream=provider_config.get("stream", False),
            ssl_verify=provider_config.get("ssl_verify", True),
        )

    raise ValueError(
        f"不支持的 provider 类型: '{backend_type}'。"
        f" 支持的类型: {list(_SUPPORTED_TYPES)}"
    )


def create_translator_from_config() -> ITranslator:
    """便捷方法：从 YAML 配置 + 环境变量创建默认 translator。

    内部流程：
    1. 加载 .env 环境变量（含 API_TOKEN）
    2. 读取 llm_providers.yaml 并获取默认 provider 配置
    3. 调用 create_translator() 完成创建

    Returns:
        默认配置的 ITranslator 实例。
    """
    load_env()
    provider_config = get_default_provider()
    return create_translator(provider_config)