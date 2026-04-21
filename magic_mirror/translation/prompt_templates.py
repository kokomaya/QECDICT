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
3. 保持编号一一对应，逐条翻译，绝对不能漏译任何一条
4. 多条文本可能属于同一个段落，翻译时请结合上下文语境理解整体含义后再翻译，确保前后文语义连贯
5. OCR 识别可能存在个别字符错误（如 l/1/I 混淆、rn/m 混淆、0/O 混淆），翻译时请根据上下文自动纠正，确保翻译通顺
6. 翻译要求准确、自然、简洁，符合中文表达习惯，不要省略信息
7. UI 元素（按钮、菜单）翻译要简短精炼
8. 专有名词保持英文原文（如 Python, GitHub, Windows）
9. 如果某条文本不是有意义的英文（如乱码、符号），原样返回
10. 严格以 JSON 数组格式输出，每一条输入都必须有对应的输出：[{"id": 1, "zh": "..."}, ...]"""


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

    # 策略 4: 正则逐条提取 id + zh（兜底：处理 LLM 输出含未转义引号等情况）
    result = _extract_all_id_zh(response_text)
    if result:
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


def parse_stream_items(accumulated: str) -> Dict[int, str]:
    """从 streaming 累积文本中增量提取已完成的 JSON 对象。

    在流式返回场景下，响应文本逐步增长。本函数用正则
    匹配所有已完成的 ``{...}`` 对象并解析。

    Args:
        accumulated: 截至目前收到的全部响应文本。

    Returns:
        已解析的 {id: zh} 映射（可能为空）。
    """
    result: Dict[int, str] = {}
    for match in re.finditer(r'\{[^{}]*\}', accumulated):
        block = match.group(0)
        try:
            obj = json.loads(block)
            item_id = obj.get("id")
            zh = obj.get("zh")
            if item_id is not None and zh is not None:
                result[int(item_id)] = str(zh)
        except (json.JSONDecodeError, ValueError, KeyError):
            # json.loads 失败（如 zh 值含未转义引号），用正则提取
            parsed = _extract_id_zh(block)
            if parsed:
                result[parsed[0]] = parsed[1]
    return result


# ------------------------------------------------------------------
# 正则兜底提取
# ------------------------------------------------------------------

def _extract_id_zh(block: str) -> Tuple[int, str] | None:
    """从单个 JSON 片段中用正则提取 id 和 zh 值。

    当 json.loads 因 zh 值含未转义引号等问题失败时使用。
    利用贪心匹配："zh": "..." 中最后一个 " 作为值的结束。
    """
    id_m = re.search(r'"id"\s*:\s*(\d+)', block)
    # 贪心 .* 从 "zh": " 后第一个字符匹配到 block 中最后一个 "
    zh_m = re.search(r'"zh"\s*:\s*"(.*)"', block, re.DOTALL)
    if id_m and zh_m:
        zh_val = zh_m.group(1).strip()
        if zh_val:
            return int(id_m.group(1)), zh_val
    return None


def _extract_all_id_zh(text: str) -> Dict[int, str]:
    """从完整响应文本中用正则逐条提取所有 id + zh 对。

    兜底策略：不依赖 json.loads，直接用正则匹配。
    """
    result: Dict[int, str] = {}
    for match in re.finditer(r'\{[^{}]*\}', text):
        parsed = _extract_id_zh(match.group(0))
        if parsed:
            result[parsed[0]] = parsed[1]
    return result