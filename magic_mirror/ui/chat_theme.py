"""聊天对话框主题 — 色彩系统与 QSS 样式表。

职责单一：只定义 ChatDialog 的视觉外观（色值、QSS），
不涉及 UI 构建或业务逻辑。
"""

# ------------------------------------------------------------------
# 色彩系统（ChatGPT 风格：深色、简洁、高可读性）
# ------------------------------------------------------------------

BG_WINDOW = "#212121"
BG_CHAT = "#212121"
BG_INPUT = "#2f2f2f"
BG_USER = "#2f2f2f"           # 用户消息背景
BG_AI = "transparent"
BG_SYSTEM = "#3a2020"

TEXT = "#ececec"
TEXT_DIM = "#8e8e8e"
TEXT_LABEL = "#ececec"         # 角色标签
TEXT_ERR = "#ef4444"

ACCENT = "#ececec"
ACCENT_DIM = "#424242"
BORDER = "#383838"

# ------------------------------------------------------------------
# QSS 样式表
# ------------------------------------------------------------------

CHAT_DIALOG_QSS = f"""
QDialog {{
    background: {BG_WINDOW};
    color: {TEXT};
}}
QLabel {{
    background: transparent;
    color: {TEXT_DIM};
}}

/* ── 顶部栏 ── */
QWidget#topBar {{
    background: {BG_WINDOW};
    border-bottom: 1px solid {BORDER};
}}
QLabel#titleLabel {{
    color: {TEXT};
    font-size: 14px;
    font-weight: 600;
}}
QLabel#tokenBadge {{
    color: {TEXT_DIM};
    font-size: 10px;
}}
QComboBox {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 12px;
}}
QComboBox:hover {{ border-color: {TEXT_DIM}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM};
    outline: 0;
}}

/* ── 输入区 ── */
QWidget#inputBar {{
    background: {BG_WINDOW};
}}
QPlainTextEdit#inputBox {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 16px;
    padding: 10px 14px;
    font-size: 13px;
    selection-background-color: rgba(255,255,255,0.15);
}}
QPlainTextEdit#inputBox:focus {{
    border-color: {TEXT_DIM};
}}

QPushButton#sendBtn {{
    background: {ACCENT};
    color: {BG_WINDOW};
    border: none;
    border-radius: 14px;
    min-width: 28px;
    min-height: 28px;
    max-width: 28px;
    max-height: 28px;
    font-size: 14px;
    font-weight: 700;
}}
QPushButton#sendBtn:hover {{
    background: #ffffff;
}}
QPushButton#sendBtn:disabled {{
    background: {ACCENT_DIM};
    color: {TEXT_DIM};
}}

/* ── 滚动条 ── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
}}
QScrollBar::handle:vertical {{
    background: {ACCENT_DIM};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""
