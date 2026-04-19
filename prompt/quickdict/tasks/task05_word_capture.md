# Task 5: 屏幕取词（UI Automation）— 实现细节

## 目标
获取鼠标光标位置下的英文单词，优先使用 Windows UI Automation API。

## 类设计

```python
class WordCapture:
    def capture(self) -> str | None
        """获取鼠标当前位置下的单词，失败返回 None"""
    
    def _capture_via_uia(self, x: int, y: int) -> str | None
        """通过 UI Automation 取词"""
    
    def _extract_word_at_cursor(self, text: str, x: int, element_rect) -> str | None
        """从文本中提取鼠标位置对应的单词"""
    
    @staticmethod
    def _clean_word(word: str) -> str | None
        """清理并验证单词"""
```

## UI Automation 取词流程

```python
import uiautomation as uia

def _capture_via_uia(self, x, y):
    # 1. 获取鼠标位置下的 UI 元素
    element = uia.ControlFromPoint(x, y)
    if element is None:
        return None
    
    # 2. 尝试获取文本内容（按优先级）
    text = None
    
    # 方式一：TextPattern（适用于富文本控件）
    try:
        pattern = element.GetTextPattern()
        if pattern:
            text = pattern.DocumentRange.GetText(-1)
    except:
        pass
    
    # 方式二：ValuePattern（适用于输入框等）
    if not text:
        try:
            pattern = element.GetValuePattern()
            if pattern:
                text = pattern.Value
        except:
            pass
    
    # 方式三：Name 属性（通用回退）
    if not text:
        text = element.Name
    
    if not text or not text.strip():
        return None
    
    # 3. 从文本中提取鼠标位置对应的单词
    rect = element.BoundingRectangle
    return self._extract_word_at_cursor(text, x, rect)
```

## 单词定位算法

鼠标 X 坐标相对于元素起始位置的比例，用来估算文本中的字符位置：

```python
def _extract_word_at_cursor(self, text, cursor_x, element_rect):
    """根据鼠标 X 坐标估算文本中的位置，提取对应单词"""
    if not text:
        return None
    
    # 估算鼠标在文本中的字符位置（等宽字体假设）
    text_width = element_rect.right - element_rect.left
    if text_width <= 0:
        # 无法估算位置，返回文本中第一个英文单词
        return self._first_english_word(text)
    
    ratio = (cursor_x - element_rect.left) / text_width
    char_pos = int(ratio * len(text))
    char_pos = max(0, min(char_pos, len(text) - 1))
    
    # 找到 char_pos 所在的单词边界
    # 向左扩展到单词开头
    start = char_pos
    while start > 0 and text[start - 1].isalpha():
        start -= 1
    
    # 向右扩展到单词结尾
    end = char_pos
    while end < len(text) and text[end].isalpha():
        end += 1
    
    word = text[start:end]
    return self._clean_word(word)
```

## 单词清理与验证

```python
import re

def _clean_word(word: str) -> str | None:
    """清理并验证提取到的单词"""
    if not word:
        return None
    
    word = word.strip()
    
    # 过滤纯数字
    if word.isdigit():
        return None
    
    # 只保留英文字母（允许连字符如 self-aware）
    if not re.match(r'^[a-zA-Z]([a-zA-Z\-]*[a-zA-Z])?$', word):
        return None
    
    # 单个字母过滤（除了 I 和 a）
    if len(word) == 1 and word.lower() not in ('i', 'a'):
        return None
    
    return word.lower()

def _split_compound(word: str) -> list[str]:
    """拆分驼峰和下划线命名"""
    # snake_case
    if '_' in word:
        return [w for w in word.split('_') if w]
    
    # camelCase / PascalCase
    parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)', word)
    if len(parts) > 1:
        return [p.lower() for p in parts]
    
    return [word]
```

## 注意事项
- `uiautomation.ControlFromPoint()` 在某些应用中可能返回空或不可读控件
- 部分应用（如 Chrome）需要启用辅助功能才能获取文本
- 等宽假设在非等宽字体中会有偏差，但对于单词定位足够（精确到附近单词即可）
- 获取 UI 元素的操作可能耗时 50-200ms，应在后台线程中执行
- 后续 Task 9 会增加 OCR 作为回退方案
