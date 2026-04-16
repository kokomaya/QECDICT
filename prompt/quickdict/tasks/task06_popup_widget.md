# Task 6: 翻译弹窗 UI — 实现细节

## 目标
实现美观的圆角卡片翻译弹窗，支持动画效果和智能定位。

## 类设计

```python
class PopupWidget(QWidget):
    closed = pyqtSignal()  # 弹窗关闭信号
    
    def __init__(self, parent=None)
    def show_word(self, data: dict, x: int, y: int)
    def hide_popup(self)
    def _adjust_position(self, x: int, y: int) -> tuple[int, int]
    def _animate_show(self)
    def _update_content(self, data: dict)
```

## 窗口属性

```python
def __init__(self, parent=None):
    super().__init__(parent)
    # 无边框 + 置顶 + 工具窗口（不在任务栏显示）
    self.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.Tool
    )
    # 背景透明（由 QSS 控制实际背景色）
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    # 固定最大宽度
    self.setMaximumWidth(420)
    self.setMinimumWidth(300)
```

## 弹窗布局结构

```
QWidget (PopupWidget)
└── QVBoxLayout (主布局, margins=0)
    └── QFrame#card (圆角卡片容器)
        └── QVBoxLayout (内部布局, margins=16)
            ├── QHBoxLayout (顶部行)
            │   ├── QLabel#word         "perceive"
            │   ├── QLabel#phonetic     "/pəˈsiːv/"
            │   ├── QSpacerItem         (弹性间距)
            │   └── QLabel#collins      "★★★☆☆"
            │
            ├── QFrame#separator_1      (分隔线)
            │
            ├── QLabel#translation      "vt. 察觉，感觉..."
            ├── QLabel#definition       "v. to become aware..."
            │
            ├── QFrame#separator_2      (分隔线)
            │
            └── QHBoxLayout (底部信息)
                ├── QLabel#freq_info    "BNC: 3218 | 当代: 2856"
                ├── QLabel#tags         "六级 GRE 雅思"
                └── QLabel#exchange     "过去式: perceived"
```

## QSS 样式（浅色模式）

```css
/* quickdict/styles/popup.qss */

QFrame#card {
    background-color: #FFFFFF;
    border-radius: 8px;
    border: 1px solid #E0E0E0;
}

QLabel#word {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 18px;
    font-weight: 700;
    color: #1A1A2E;
}

QLabel#phonetic {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    color: #6C757D;
    padding-left: 8px;
}

QLabel#collins {
    font-size: 14px;
    color: #F5A623;
}

QFrame#separator_1, QFrame#separator_2 {
    background-color: #F0F0F0;
    max-height: 1px;
    min-height: 1px;
}

QLabel#translation {
    font-family: "Microsoft YaHei UI", sans-serif;
    font-size: 14px;
    color: #1A1A2E;
    line-height: 1.5;
}

QLabel#definition {
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
    color: #6C757D;
    line-height: 1.4;
}

QLabel#freq_info {
    font-size: 11px;
    color: #9E9E9E;
}

QLabel#tags {
    font-size: 11px;
    color: #4361EE;
    font-weight: 500;
}

QLabel#exchange {
    font-size: 11px;
    color: #9E9E9E;
}
```

## 阴影效果

```python
from PyQt6.QtWidgets import QGraphicsDropShadowEffect

shadow = QGraphicsDropShadowEffect()
shadow.setBlurRadius(20)
shadow.setColor(QColor(0, 0, 0, 40))  # 半透明黑色
shadow.setOffset(0, 4)
self.card_frame.setGraphicsEffect(shadow)
```

## 弹出动画

```python
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QParallelAnimationGroup

def _animate_show(self):
    # 淡入动画
    self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
    self.fade_anim.setDuration(150)
    self.fade_anim.setStartValue(0.0)
    self.fade_anim.setEndValue(1.0)
    self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    
    # 上滑动画（从下方 8px 处滑入）
    target_pos = self.pos()
    self.move(target_pos.x(), target_pos.y() + 8)
    self.slide_anim = QPropertyAnimation(self, b"pos")
    self.slide_anim.setDuration(150)
    self.slide_anim.setStartValue(self.pos())
    self.slide_anim.setEndValue(target_pos)
    self.slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    
    # 并行执行
    self.anim_group = QParallelAnimationGroup()
    self.anim_group.addAnimation(self.fade_anim)
    self.anim_group.addAnimation(self.slide_anim)
    self.anim_group.start()
```

## 智能定位

```python
def _adjust_position(self, x, y):
    """确保弹窗不超出屏幕边界"""
    from PyQt6.QtWidgets import QApplication
    screen = QApplication.screenAt(QPoint(x, y))
    if screen is None:
        screen = QApplication.primaryScreen()
    screen_rect = screen.availableGeometry()
    
    popup_width = self.sizeHint().width()
    popup_height = self.sizeHint().height()
    
    # 默认：鼠标右下方偏移 (16, 20)
    final_x = x + 16
    final_y = y + 20
    
    # 右侧溢出 → 移到鼠标左侧
    if final_x + popup_width > screen_rect.right():
        final_x = x - popup_width - 8
    
    # 下方溢出 → 移到鼠标上方
    if final_y + popup_height > screen_rect.bottom():
        final_y = y - popup_height - 8
    
    # 确保不超出左/上边界
    final_x = max(screen_rect.left(), final_x)
    final_y = max(screen_rect.top(), final_y)
    
    return final_x, final_y
```

## 关闭行为

弹窗在以下情况关闭：
1. 用户按 Esc 键 → 通过 `keyPressEvent` 捕获
2. 用户鼠标点击弹窗外区域 → 全局鼠标事件监听
3. 取词模式被关闭 → 主程序调用 `hide_popup()`
4. 鼠标移动到新单词 → 先隐藏旧弹窗，查询后显示新弹窗

## 释义文本处理
- `translation` 和 `definition` 中的 `\n` 拆分为多行显示
- 最多显示 3 行释义，超出部分截断并显示 "..."
- QLabel 启用 `setWordWrap(True)` 自动换行
- 中文释义使用 Microsoft YaHei UI 字体确保渲染清晰
