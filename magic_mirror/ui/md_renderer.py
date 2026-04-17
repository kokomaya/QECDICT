"""Markdown → HTML 渲染器 — 将 LLM 响应转为富文本 HTML。

职责单一：负责 Markdown 文本 → styled HTML 转换，
以及聊天消息级别的 HTML 组合。不涉及 UI 组件或网络调用。
"""

from __future__ import annotations

import html as html_mod

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension

from magic_mirror.ui.chat_theme import (
    TEXT_DIM,
    TEXT_ERR,
)

# Pygments 代码高亮 — 暗色主题内联样式
_MD = markdown.Markdown(
    extensions=[
        "fenced_code",
        "tables",
        "sane_lists",
        CodeHiliteExtension(noclasses=True, pygments_style="monokai"),
    ],
)

# 富文本 CSS（ChatGPT 风格：简洁、居中、高可读性）
MESSAGE_CSS = """\
body {
    font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
    font-size: 14px;
    line-height: 1.7;
    color: #ececec;
    margin: 0;
    padding: 0;
    background: #212121;
}
.msg-row { padding: 20px 0; }
.msg-row + .msg-row { border-top: 1px solid rgba(255,255,255,0.06); }
.msg-inner {
    max-width: 680px;
    margin: 0 auto;
    padding: 0 24px;
}
.role-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px; height: 24px;
    border-radius: 50%;
    font-size: 12px;
    font-weight: 700;
    margin-right: 8px;
    vertical-align: middle;
    flex-shrink: 0;
}
.role-icon.human { background: #19c37d; color: #fff; }
.role-icon.ai     { background: #ab68ff; color: #fff; }
.role-icon.err    { background: #ef4444; color: #fff; }
.role-label {
    font-weight: 600;
    font-size: 13px;
    color: #ececec;
    vertical-align: middle;
}
.role-header { margin-bottom: 6px; }
.msg-content { color: #d1d5db; font-size: 14px; line-height: 1.7; }
.msg-content p { margin: 6px 0; }

/* markdown elements */
ul, ol { margin: 6px 0 6px 20px; padding: 0; }
li { margin: 3px 0; }
h1, h2, h3, h4 { color: #ececec; margin: 12px 0 6px 0; font-weight: 600; }
h1 { font-size: 18px; } h2 { font-size: 16px; } h3 { font-size: 15px; }
strong { color: #ffffff; }
em { font-style: italic; }
a { color: #58a6ff; text-decoration: none; }
code {
    background: #2f2f2f;
    color: #e06c75;
    padding: 1px 5px;
    border-radius: 4px;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 13px;
}
pre {
    background: #1a1a1a;
    border: 1px solid #383838;
    border-radius: 8px;
    padding: 12px 16px;
    overflow-x: auto;
    margin: 8px 0;
}
pre code {
    background: transparent;
    color: inherit;
    padding: 0;
    font-size: 13px;
    line-height: 1.5;
}
table { border-collapse: collapse; margin: 8px 0; }
th, td { border: 1px solid #383838; padding: 6px 12px; font-size: 13px; }
th { background: #2f2f2f; color: #ececec; }
td { background: #1a1a1a; }
blockquote {
    border-left: 3px solid #ab68ff;
    margin: 8px 0;
    padding: 4px 14px;
    color: #8e8e8e;
    background: rgba(255,255,255,0.03);
    border-radius: 0 6px 6px 0;
}
hr { border: none; border-top: 1px solid #383838; margin: 10px 0; }

/* streaming indicator */
.streaming-dot {
    padding: 4px 0;
    color: #8e8e8e;
    font-size: 12px;
    max-width: 680px;
    margin: 0 auto;
    padding-left: 24px;
}
"""


import re as _re

# 预处理：在列表/代码块/标题前自动补空行（LLM 输出常缺少）
_BLOCK_START = _re.compile(
    r"(?<!\n\n)"           # 前面不是空行
    r"(?<=\n)"             # 前面是换行
    r"([ \t]*[-*+] |\d+\. |```|#{1,6} )",  # 列表/代码块/标题起始
)


def _ensure_blank_lines(text: str) -> str:
    """在 Markdown 块级元素前补空行，确保解析器识别。"""
    return _BLOCK_START.sub(r"\n\1", text)


def render_markdown(text: str) -> str:
    """将 Markdown 文本转换为带内联样式的 HTML 片段。"""
    _MD.reset()
    html_body = _MD.convert(_ensure_blank_lines(text))
    return html_body


# ------------------------------------------------------------------
# 消息级 HTML 组合
# ------------------------------------------------------------------

_MSG_TEMPLATE = """\
<div class="msg-row">
  <div class="msg-inner">
    <div class="role-header">
      <span class="role-icon {role_class}">{icon}</span>
      <span class="role-label">{label}</span>
    </div>
    <div class="msg-content">{content}</div>
  </div>
</div>
"""


def render_message(role: str, text: str) -> str:
    """将单条聊天消息（含角色）渲染为完整 HTML 片段。"""
    if role == "human":
        content = html_mod.escape(text).replace("\n", "<br>")
        return _MSG_TEMPLATE.format(
            role_class="human", icon="U", label="You",
            content=content,
        )

    if role == "assistant":
        content = render_markdown(text) if text else f'<span style="color:{TEXT_DIM};">…</span>'
        return _MSG_TEMPLATE.format(
            role_class="ai", icon="M", label="Magic Mirror",
            content=content,
        )

    # error
    content = f'<span style="color:{TEXT_ERR}">{html_mod.escape(text)}</span>'
    return _MSG_TEMPLATE.format(
        role_class="err", icon="!", label="Error",
        content=content,
    )


def build_messages_html(
    messages: list[dict],
    *,
    streaming: bool = False,
) -> str:
    """将消息列表组合为完整的 HTML body（含 <style>）。

    Parameters
    ----------
    messages : [{"role": str, "text": str}, ...]
    streaming : 是否显示 "generating…" 指示
    """
    parts: list[str] = []
    for msg in messages:
        parts.append(render_message(msg["role"], msg["text"]))
    if streaming:
        parts.append(
            '<div class="streaming-dot">● generating…</div>'
        )
    return "".join(parts)
