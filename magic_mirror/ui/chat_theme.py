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
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel {{
    background: transparent;
    color: {TEXT_DIM};
}}

/* ── 自定义标题栏 ── */
QWidget#titleBar {{
    background: #1a1a1a;
    border-bottom: 1px solid {BORDER};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QLabel#titleIcon {{
    color: #0078d7;
    font-size: 14px;
    background: transparent;
}}
QLabel#titleBarLabel {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}}
QLabel#tokenBadge {{
    color: {TEXT_DIM};
    font-size: 10px;
    background: transparent;
}}
QPushButton#titleBtnMin, QPushButton#titleBtnClose {{
    background: transparent;
    color: {TEXT_DIM};
    border: none;
    border-radius: 4px;
    font-size: 13px;
}}
QPushButton#titleBtnMin:hover {{
    background: rgba(255, 255, 255, 0.1);
    color: {TEXT};
}}
QPushButton#titleBtnClose:hover {{
    background: #c42b1c;
    color: #ffffff;
}}

/* ── 模型选择框 ── */
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

/* ── 拖拽调整大小手柄 ── */
QSizeGrip#sizeGrip {{
    background: transparent;
    width: 12px;
    height: 12px;
}}
"""
