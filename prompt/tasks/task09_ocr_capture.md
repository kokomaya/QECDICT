# Task 9: OCR 备用取词 — 实现细节

## 目标
当 UI Automation 无法取词时（图片、PDF、游戏等），使用 OCR 截屏识别作为回退方案。

## 修改位置
更新 `quickdict/word_capture.py` 的 `WordCapture` 类。

## 新增方法

```python
class WordCapture:
    # ... 已有方法 ...
    
    def _capture_via_ocr(self, x: int, y: int) -> str | None:
        """通过 OCR 截屏取词"""
    
    def capture(self) -> str | None:
        """主入口：先 UIA，失败回退 OCR"""
        x, y = self._get_cursor_pos()
        word = self._capture_via_uia(x, y)
        if word:
            return word
        return self._capture_via_ocr(x, y)
```

## OCR 取词流程

```python
from PIL import ImageGrab
from rapidocr_onnxruntime import RapidOCR

class WordCapture:
    def __init__(self):
        self._ocr = None  # 懒加载
    
    def _get_ocr(self):
        if self._ocr is None:
            self._ocr = RapidOCR()
        return self._ocr
    
    def _capture_via_ocr(self, x, y):
        # 1. 截取鼠标周围区域（200×60 像素）
        region = (x - 100, y - 30, x + 100, y + 30)
        screenshot = ImageGrab.grab(bbox=region)
        
        # 2. DPI 缩放处理
        # Windows 缩放比例可能导致坐标偏移，需获取实际缩放因子
        import ctypes
        scale = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
        if scale != 1.0:
            actual_region = (
                int(region[0] * scale),
                int(region[1] * scale),
                int(region[2] * scale),
                int(region[3] * scale)
            )
            screenshot = ImageGrab.grab(bbox=actual_region)
        
        # 3. OCR 识别
        ocr = self._get_ocr()
        result, _ = ocr(screenshot)
        
        if not result:
            return None
        
        # 4. 从 OCR 结果中提取鼠标位置对应的单词
        # result 格式: [[box, text, confidence], ...]
        # box 是四个角点坐标，text 是识别文字
        
        # 鼠标在截图中的相对位置是中心点 (100, 30)
        cursor_rel_x = 100
        cursor_rel_y = 30
        
        best_word = None
        best_distance = float('inf')
        
        for box, text, confidence in result:
            if confidence < 0.5:
                continue
            
            # 计算文本框中心
            box_center_x = sum(p[0] for p in box) / 4
            box_center_y = sum(p[1] for p in box) / 4
            
            # 计算距离
            dist = ((box_center_x - cursor_rel_x) ** 2 + 
                    (box_center_y - cursor_rel_y) ** 2) ** 0.5
            
            if dist < best_distance:
                # 从识别文本中提取最近的英文单词
                words = re.findall(r'[a-zA-Z]+', text)
                if words:
                    # 估算鼠标在文本中的位置
                    box_left = min(p[0] for p in box)
                    box_right = max(p[0] for p in box)
                    ratio = (cursor_rel_x - box_left) / max(box_right - box_left, 1)
                    char_pos = int(ratio * len(text))
                    
                    # 找最近的单词
                    nearest = self._nearest_word(text, char_pos, words)
                    if nearest:
                        best_distance = dist
                        best_word = nearest
        
        return self._clean_word(best_word)
```

## 性能优化
- **懒加载 OCR 模型**：首次使用时才加载 RapidOCR，避免启动耗时
- **截图区域最小化**：只截 200×60 区域，OCR 耗时约 50-100ms
- **缓存截图去重**：如果鼠标位置未移动超过 10px，不重新截屏
- **降级策略**：如果 RapidOCR 未安装，gracefully 跳过 OCR，只使用 UIA

## DPI 缩放处理
```python
import ctypes

def _get_dpi_scale():
    """获取当前显示器的 DPI 缩放比例"""
    try:
        # Windows 10+
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except:
        return 1.0
```

## 注意事项
- RapidOCR 的 ONNX 模型文件约 10MB，打包时需包含
- OCR 识别英文的准确率较高（>95%），但对小号字体或模糊文字可能失败
- 截图时要处理多显示器场景（坐标可能为负数）
- `ImageGrab.grab()` 在 Windows 上需要 DPI awareness 设置才能正确截图
