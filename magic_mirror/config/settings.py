"""应用通用配置 — 不包含任何后端 URL / IP / 凭证"""

# ── 热键 ──
HOTKEY_TRIGGER = "ctrl+alt+t"
HOTKEY_OCR_COPY = "ctrl+alt+c"         # OCR 提取原文并复制到剪贴板

# ── OCR ──
OCR_CONFIDENCE_THRESHOLD = 0.5
OCR_DET_BOX_THRESH = 0.3

# ── UI: 覆盖层 ──
OVERLAY_OPACITY = 255                       # 覆盖层不透明度 (0-255)

# ── UI: 区域框选 ──
SELECTOR_MASK_COLOR = (0, 0, 0, 80)         # 框选遮罩颜色 RGBA
SELECTOR_BORDER_COLOR = (0, 120, 215)       # 框选边框颜色 RGB

# ── 排版 ──
FONT_FAMILY_ZH = "Microsoft YaHei"         # 中文渲染字体
FONT_SIZE_SCALE = 1.0                       # 字号像素缩放系数（1.0 = OCR bbox 高度）
MAX_FONT_SHRINK_RATIO = 0.6                 # 最大字号缩小比例
