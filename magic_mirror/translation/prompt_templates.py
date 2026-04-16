"""翻译 Prompt 模板 — 集中管理所有 AI Prompt，与翻译后端实现解耦。

职责单一：只负责 Prompt 的构建和响应的解析，
不涉及 API 调用、网络请求或配置加载。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是一个专业的英中翻译引擎，专门用于屏幕文本的实时翻译。

规则：
1. 将输入的英文文本翻译为简体中文
2. 输入是一组带编号的文本片段，来自屏幕截图的 OCR 识别
3. 保持编号一一对应，逐条翻译
4. 翻译要求自然、简洁，符合中文表达习惯
5. UI 元素（按钮、菜单）翻译要简短精炼
6. 专有名词保持英文原文（如 Python, GitHub, Windows）
7. 如果某条文本不是有意义的英文（如乱码、符号），原样返回
8. 严格以 JSON 数组格式输出：[{"id": 1, "zh": "..."}, ...]"""


def build_user_prompt(texts: List[Tuple[int, str]]) -> str:
    """构建用户 Prompt。

    Args:
        texts: [(id, text), ...] 编号文本列表。

    Returns:
        格式化的编号文本字符串。

    Example:
        >>> build_user_prompt([(1, "File"), (2, "Edit")])
        '请翻译以下文本：\\n1. File\\n2. Edit'
    """
    lines = ["请翻译以下文本："]
    for idx, text in texts:
        lines.append(f"{idx}. {text}")
    return "\n".join(lines)


def parse_translation_response(response_text: str) -> Dict[int, str]:
    """解析 AI 返回的翻译 JSON 响应。

    尝试多种策略解析，兼容 AI 返回非标准 JSON 的情况。

    Args:
        response_text: AI 返回的原始文本。

    Returns:
        {id: translated_text} 映射。解析失败返回空字典。

    Example:
        >>> parse_translation_response('[{"id": 1, "zh": "文件"}]')
        {1: '文件'}
    """
    # 策略 1: 直接解析整段文本
    result = _try_parse_json(response_text)
    if result is not None:
        return result

    # 策略 2: 提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", response_text, re.DOTALL)
    if match:
        result = _try_parse_json(match.group(1))
        if result is not None:
            return result

    # 策略 3: 提取最外层方括号 [...] 片段
    match = re.search(r"\[.*\]", response_text, re.DOTALL)
    if match:
        result = _try_parse_json(match.group(0))
        if result is not None:
            return result

    logger.warning("无法解析翻译响应: %s", response_text[:200])
    return {}


def _try_parse_json(text: str) -> Dict[int, str] | None:
    """尝试将文本解析为 [{id, zh}, ...] 格式的 JSON 数组。

    Returns:
        解析成功返回 {id: zh} 映射，失败返回 None。
    """
    try:
        data = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, list):
        return None

    mapping: Dict[int, str] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        zh = item.get("zh")
        if item_id is not None and zh is not None:
            mapping[int(item_id)] = str(zh)

    return mapping if mapping else None