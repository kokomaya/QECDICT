"""应用通用配置 — 不包含任何后端 URL / IP / 凭证"""

# ── 热键 ──
HOTKEY_TRIGGER = "ctrl+alt+t"
HOTKEY_OCR_COPY = "ctrl+alt+c"         # OCR 提取原文并复制到剪贴板
HOTKEY_CHAT = "ctrl+alt+d"             # 选中文本后直接 AI 聊天

# ── OCR ──
OCR_CONFIDENCE_THRESHOLD = 0.5
OCR_TEXT_SCORE = 0.35                       # 最终文本置信度过滤（降低以减少漏检）
OCR_DET_BOX_THRESH = 0.3
OCR_DET_BOX_THRESH_LOW = 0.15               # 低阈值二次检测，补漏遗漏文本
OCR_DET_LIMIT_SIDE_LEN = 960                # 检测输入图像最小边（增大以提升小文字检测）
OCR_DET_UNCLIP_RATIO = 1.8                  # 检测框扩展比例（增大以减少文字截断）
OCR_USE_GPU = True                          # 启用 GPU 加速（DirectML，自动回退 CPU）
OCR_CC_VERIFY_ENABLED = True                # 连通分量验证补漏
OCR_PAD_BORDER = 12                         # 边界填充像素数（0 = 禁用）

# ── UI: 覆盖层 ──
OVERLAY_OPACITY = 255                       # 覆盖层不透明度 (0-255)

# ── UI: 区域框选 ──
SELECTOR_MASK_COLOR = (0, 0, 0, 80)         # 框选遮罩颜色 RGBA
SELECTOR_BORDER_COLOR = (0, 120, 215)       # 框选边框颜色 RGB

# ── 排版 ──
FONT_FAMILY_ZH = "Microsoft YaHei"         # 中文渲染字体
FONT_FAMILY_ZH_SERIF = "Noto Serif SC"     # 中文衬线字体
FONT_FAMILY_EN_SERIF = "Times New Roman"   # 英文衬线字体
FONT_FAMILY_EN_SANS = "Segoe UI"           # 英文无衬线字体
FONT_SIZE_SCALE = 1.0                       # 字号像素缩放系数（1.0 = OCR bbox 高度）
MAX_FONT_SHRINK_RATIO = 0.6                 # 最大字号缩小比例

# ── 字体检测 ──
FONT_DETECT_ENABLED = True
FONT_BOLD_THRESHOLD = 0.075                 # 笔画宽度比阈值（ratio = stroke_w / font_size_est）
FONT_ITALIC_THRESHOLD = 8.0                 # 斜体角度阈值（度）
FONT_SERIF_CV_THRESHOLD = 0.8              # run-length 变异系数阈值
