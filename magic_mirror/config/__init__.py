"""配置加载器 — 负责加载 LLM 后端配置和环境变量凭证"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

_CONFIG_DIR = Path(__file__).resolve().parent

_LLM_CONFIG_FILE = _CONFIG_DIR / "llm_providers.yaml"
_LLM_EXAMPLE_FILE = _CONFIG_DIR / "llm_providers.example.yaml"
_ENV_FILE = _CONFIG_DIR / ".env"


def load_env() -> None:
    """加载 config/.env 中的环境变量到 os.environ。

    文件不存在时静默跳过（凭证可能通过系统环境变量注入）。
    """
    load_dotenv(_ENV_FILE)


def load_llm_config() -> dict:
    """加载 llm_providers.yaml 并返回完整配置字典。

    Raises:
        FileNotFoundError: 配置文件不存在时，给出明确提示。
    """
    if not _LLM_CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"LLM 配置文件不存在: {_LLM_CONFIG_FILE}\n"
            f"请复制示例文件并填入实际值:\n"
            f"  copy {_LLM_EXAMPLE_FILE} {_LLM_CONFIG_FILE}"
        )

    with open(_LLM_CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config or "providers" not in config:
        raise ValueError(
            f"LLM 配置文件格式错误: {_LLM_CONFIG_FILE}\n"
            f"请参考 {_LLM_EXAMPLE_FILE} 的格式填写。"
        )

    return config


def get_default_provider() -> dict:
    """返回默认 provider 的完整配置（含 api_key）。

    自动从 os.environ 读取 API_TOKEN 并注入到返回的配置中。

    Raises:
        FileNotFoundError: 配置文件不存在。
        KeyError: 默认 provider 未定义或不存在。
    """
    config = load_llm_config()
    default_name = config.get("default_provider")

    if not default_name:
        raise KeyError(
            f"llm_providers.yaml 中未指定 default_provider 字段。"
        )

    providers = config.get("providers", {})
    if default_name not in providers:
        raise KeyError(
            f"默认 provider '{default_name}' 在 providers 中不存在。\n"
            f"可用的 providers: {list(providers.keys())}"
        )

    provider = dict(providers[default_name])

    # 从环境变量注入凭证，不在配置文件中存储
    api_token = os.environ.get("API_TOKEN")
    if api_token:
        provider["api_key"] = api_token

    return provider