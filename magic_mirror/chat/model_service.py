"""模型服务 — 列出可用模型 & 持久化用户选择。

职责单一：只负责从 API 获取模型列表、读写用户选择的模型名，
不涉及聊天逻辑或 UI 渲染。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

import httpx
import openai

from magic_mirror.config import get_default_provider, load_env

logger = logging.getLogger(__name__)

# 用户选择的模型持久化文件
_PREFS_FILE = Path(__file__).resolve().parent.parent / "config" / "user_prefs.json"


def list_models() -> List[str]:
    """从 LLM 后端获取可用模型列表（不做持久化缓存）。"""
    load_env()
    provider = get_default_provider()

    http_client = httpx.Client(
        verify=provider.get("ssl_verify", True),
    ) if not provider.get("ssl_verify", True) else None

    client = openai.OpenAI(
        api_key=provider.get("api_key", "unused"),
        base_url=provider["base_url"],
        default_headers=provider.get("headers", {}),
        timeout=provider.get("timeout", 60),
        http_client=http_client,
    )

    try:
        response = client.models.list()
        models = [m.id for m in response.data]
        logger.info("获取到 %d 个可用模型", len(models))
        return models
    except Exception as exc:
        logger.error("获取模型列表失败: %s", exc)
        return []


def load_selected_model() -> Optional[str]:
    """读取用户持久化的模型选择，不存在则返回 None。"""
    if not _PREFS_FILE.exists():
        return None
    try:
        data = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        return data.get("chat_model")
    except Exception:
        return None


def save_selected_model(model_name: str) -> None:
    """将用户选择的模型名写入持久化文件。"""
    data: dict = {}
    if _PREFS_FILE.exists():
        try:
            data = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["chat_model"] = model_name
    _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PREFS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("已保存模型选择: %s", model_name)
