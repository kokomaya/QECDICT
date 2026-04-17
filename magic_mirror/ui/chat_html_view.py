"""聊天消息 HTML 视图 — 基于 QWebEngineView 的富文本渲染组件。

职责单一：只负责将 HTML 字符串渲染到内嵌浏览器视图中，
提供自动滚动到底部的能力。不涉及消息构建或业务逻辑。
"""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget

from magic_mirror.ui.md_renderer import MESSAGE_CSS


class ChatHtmlView(QWebEngineView):
    """内嵌 Chromium 视图 — 渲染聊天消息 HTML。

    页面 Shell（含 CSS）只加载一次，后续消息更新通过
    JavaScript `innerHTML` 注入，避免 setHtml 触发的完整导航。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # 允许默认右键菜单（选中/复制）
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._page_ready = False
        self.page().loadFinished.connect(self._on_shell_ready)
        self.setHtml(self._build_shell(), QUrl("about:blank"))
        # 缓存：页面就绪前的待渲染 HTML
        self._pending_html: str | None = None

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def set_messages_html(self, body_html: str) -> None:
        """将消息 HTML 注入到页面 <div id="root"> 中（DOM 级更新，无导航）。"""
        if not self._page_ready:
            self._pending_html = body_html
            return
        safe = json.dumps(body_html)
        js = (
            f"document.getElementById('root').innerHTML = {safe};"
            "if ((window.innerHeight + window.scrollY) >= document.body.scrollHeight - 60"
            " || document.body.scrollHeight <= window.innerHeight) {"
            "  window.scrollTo(0, document.body.scrollHeight);"
            "}"
        )
        self.page().runJavaScript(js)

    def clear_view(self) -> None:
        if self._page_ready:
            self.page().runJavaScript("document.getElementById('root').innerHTML = '';")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _on_shell_ready(self, ok: bool) -> None:
        """Shell 首次加载完成后标记就绪，刷出待渲染内容。"""
        self.page().loadFinished.disconnect(self._on_shell_ready)
        self._page_ready = True
        if self._pending_html is not None:
            self.set_messages_html(self._pending_html)
            self._pending_html = None

    @staticmethod
    def _build_shell() -> str:
        copy_btn_css = (
            ".copy-btn {"
            "  position:absolute; top:6px; right:6px;"
            "  background:rgba(255,255,255,0.1); color:#aaa;"
            "  border:1px solid rgba(255,255,255,0.15); border-radius:4px;"
            "  padding:2px 8px; font-size:11px; cursor:pointer;"
            "  opacity:0; transition:opacity 0.15s;"
            "}"
            ".copy-btn:hover { background:rgba(255,255,255,0.2); color:#fff; }"
            ".code-wrapper { position:relative; }"
            ".code-wrapper:hover .copy-btn { opacity:1; }"
            ".msg-row { position:relative; }"
            ".msg-copy-btn {"
            "  position:absolute; top:12px; right:12px;"
            "  background:rgba(255,255,255,0.06); color:#666;"
            "  border:1px solid rgba(255,255,255,0.1); border-radius:4px;"
            "  padding:2px 8px; font-size:11px; cursor:pointer;"
            "  opacity:0; transition:opacity 0.15s;"
            "}"
            ".msg-copy-btn:hover { background:rgba(255,255,255,0.15); color:#ccc; }"
            ".msg-row:hover .msg-copy-btn { opacity:1; }"
        )
        copy_btn_js = (
            "<script>"
            "document.addEventListener('click', function(e) {"
            "  var btn = e.target.closest('.copy-btn');"
            "  if (btn) {"
            "    var code = btn.parentElement.querySelector('pre code, pre');"
            "    if (code) {"
            "      navigator.clipboard.writeText(code.innerText).then(function(){"
            "        btn.textContent='Copied!'; setTimeout(function(){btn.textContent='Copy';},1200);"
            "      });"
            "    }"
            "    return;"
            "  }"
            "  var mbtn = e.target.closest('.msg-copy-btn');"
            "  if (mbtn) {"
            "    var content = mbtn.parentElement.querySelector('.msg-content');"
            "    if (content) {"
            "      navigator.clipboard.writeText(content.innerText).then(function(){"
            "        mbtn.textContent='Copied!'; setTimeout(function(){mbtn.textContent='Copy';},1200);"
            "      });"
            "    }"
            "  }"
            "});"
            "</script>"
        )
        return (
            "<!DOCTYPE html>"
            '<html><head><meta charset="utf-8"><style>'
            "html, body { margin:0; padding:0; }"
            "body { background:#212121; }"
            f"{MESSAGE_CSS}"
            f"{copy_btn_css}"
            "::-webkit-scrollbar { width:6px; }"
            "::-webkit-scrollbar-track { background:transparent; }"
            "::-webkit-scrollbar-thumb { background:#424242; border-radius:3px; }"
            "</style></head><body>"
            '<div id="root"></div>'
            f"{copy_btn_js}"
            "</body></html>"
        )
