# QuickDict — 开发任务清单

> 按优先级分阶段，每个 Task 为一个可独立完成和验证的最小工作单元。  
> 复杂任务的实现细节见 `prompt/tasks/` 目录下的对应文件。

---

## P0 — 核心 MVP（最小可用版本）

### Task 1: 项目脚手架搭建
- **目标**：创建项目目录结构、虚拟环境、依赖文件
- **产出文件**：`quickdict/` 目录、`requirements.txt`
- **步骤**：
  1. 创建 `quickdict/` 目录及子目录 `styles/`、`assets/`
  2. 创建各模块空文件：`main.py`、`app.py`、`hotkey.py`、`word_capture.py`、`dict_engine.py`、`popup_widget.py`、`overlay_widget.py`、`config.py`、`utils.py`
  3. 编写 `requirements.txt`，包含所有依赖及版本约束
  4. 在 `.venv` 虚拟环境中安装依赖：`pip install -r quickdict/requirements.txt`
- **验收**：`import PyQt6, pynput, uiautomation` 等均不报错

---

### Task 2: CSV 导入 SQLite 数据库
- **目标**：将 `ecdict.csv` 转换为 `ecdict.db` SQLite 数据库
- **产出文件**：`quickdict/build_db.py`（一次性脚本）
- **详细说明**：[tasks/task02_build_db.md](tasks/task02_build_db.md)
- **步骤**：
  1. 复用 `stardict.py` 的 `StarDict` 类创建数据库
  2. 逐行读取 `ecdict.csv`，调用 `register()` + `update()` 写入
  3. 构建 lemma 反查表（从 exchange 字段提取变形→原形映射），存入额外表 `lemma`
  4. 生成 `ecdict.db` 置于 `quickdict/data/` 目录
- **验收**：`StarDict('ecdict.db').query('perceive')` 返回完整词条；`lemma` 表可查 `perceived → perceive`

---

### Task 3: 词典查询引擎
- **目标**：封装 ECDICT 查询逻辑，支持多级回退查询
- **产出文件**：`quickdict/dict_engine.py`
- **详细说明**：[tasks/task03_dict_engine.md](tasks/task03_dict_engine.md)
- **步骤**：
  1. 封装 `DictEngine` 类，初始化时打开 SQLite 连接并常驻
  2. 实现 `lookup(word) -> dict | None` 方法，查询策略：
     - 精确匹配（大小写不敏感）
     - lemma 反查表还原词形后再查
     - `stripword()` 处理后模糊匹配
     - `match()` 返回候选词
  3. 实现 LRU 缓存（`functools.lru_cache` 或手动，容量 500）
  4. 实现结果格式化：将 `collins` 转星级、`tag` 转中文标签、`exchange` 解析为可读格式
- **验收**：`DictEngine.lookup('perceived')` 返回 perceive 的完整格式化结果

---

### Task 4: 全局快捷键监听
- **目标**：检测连按两次 Ctrl 键激活取词模式
- **产出文件**：`quickdict/hotkey.py`
- **详细说明**：[tasks/task04_hotkey.md](tasks/task04_hotkey.md)
- **步骤**：
  1. 使用 `pynput.keyboard.Listener` 监听全局键盘事件
  2. 实现连按检测：记录 Ctrl 键的 press/release 时间戳，500ms 内连续两次 press-release 视为激活
  3. 检测 Esc 键用于退出取词模式
  4. 通过回调函数 `on_activate` / `on_deactivate` 通知主程序
  5. 确保监听运行在独立线程，不阻塞 Qt 事件循环
- **验收**：独立运行 hotkey.py，连按 Ctrl 打印 "activated"，按 Esc 打印 "deactivated"

---

### Task 5: 屏幕取词（UI Automation）
- **目标**：获取鼠标位置下的英文单词
- **产出文件**：`quickdict/word_capture.py`
- **详细说明**：[tasks/task05_word_capture.md](tasks/task05_word_capture.md)
- **步骤**：
  1. 使用 `uiautomation` 库获取鼠标位置下的 UI 元素
  2. 读取元素的 `Name` 或 `Value` 属性获取文本内容
  3. 根据鼠标 X 坐标在文本中定位最近的英文单词（空格/标点分割）
  4. 过滤非英文字符（纯数字、符号等）
  5. 处理驼峰命名 `camelCase` 和下划线命名 `snake_case` 的拆分
  6. 封装为 `WordCapture` 类，提供 `capture() -> str | None` 方法
- **验收**：将鼠标悬停在浏览器/编辑器文字上，调用 `capture()` 正确返回单词

---

### Task 6: 翻译弹窗 UI
- **目标**：实现美观的圆角卡片翻译弹窗
- **产出文件**：`quickdict/popup_widget.py`、`quickdict/styles/popup.qss`
- **详细说明**：[tasks/task06_popup_widget.md](tasks/task06_popup_widget.md)
- **步骤**：
  1. 继承 `QWidget` 创建 `PopupWidget`，设置 `FramelessWindowHint` + `WindowStaysOnTopHint`
  2. 使用 QSS 实现圆角(8px)、阴影(QGraphicsDropShadowEffect)、配色
  3. 布局区域：
     - 顶部：单词 + 音标 + 柯林斯星级
     - 中部：中文释义 + 英文释义（各最多显示 3 行，超出折叠）
     - 底部：词频信息 | 考试标签 | 词形变化
  4. 实现 `show_word(data: dict, x: int, y: int)` 方法
  5. 弹窗位置智能调整：避免超出屏幕边界，自动翻转方向
  6. 弹出动画：淡入(QPropertyAnimation on windowOpacity) + 上滑(geometry)，150ms
  7. 点击弹窗外区域关闭（`focusOutEvent` 或全局鼠标监听）
- **验收**：手动调用 `show_word()` 传入测试数据，弹窗正确显示在指定位置

---

### Task 7: 主程序集成 & 端到端联调
- **目标**：将各模块串联，实现完整的取词翻译流程
- **产出文件**：`quickdict/main.py`
- **步骤**：
  1. 初始化 `QApplication`
  2. 创建 `DictEngine`、`HotkeyListener`、`WordCapture`、`PopupWidget` 实例
  3. 连接信号流：
     - `HotkeyListener.on_activate` → 进入取词模式
     - 鼠标移动事件(QTimer 轮询 200ms) → `WordCapture.capture()` → `DictEngine.lookup()` → `PopupWidget.show_word()`
     - `HotkeyListener.on_deactivate` 或 `Esc` → 关闭弹窗，退出取词模式
  4. 处理取词模式状态切换
  5. 端到端测试：连按 Ctrl → 鼠标移到单词上 → 弹出翻译 → 按 Esc 关闭
- **验收**：完整流程可用，从唤起到翻译到关闭

---

## P1 — 功能增强

### Task 8: 系统托盘 & 后台常驻
- **目标**：程序最小化到系统托盘，提供右键菜单
- **产出文件**：`quickdict/app.py`、`quickdict/assets/icon.png`
- **步骤**：
  1. 创建 `QSystemTrayIcon`，设置托盘图标（生成一个简单的字典图标 PNG）
  2. 右键菜单项：开启/关闭取词、设置、查词历史、退出
  3. 关闭主窗口时最小化到托盘而非退出
  4. 托盘图标双击打开设置/主窗口
  5. 开启/关闭取词菜单项控制 `HotkeyListener` 的启停
- **验收**：程序启动后出现在托盘区，右键菜单可操作

---

### Task 9: OCR 备用取词
- **目标**：在 UI Automation 失败时回退到 OCR 取词
- **产出文件**：更新 `quickdict/word_capture.py`
- **详细说明**：[tasks/task09_ocr_capture.md](tasks/task09_ocr_capture.md)
- **步骤**：
  1. 安装 `rapidocr-onnxruntime`
  2. 截取鼠标周围 200×60 像素区域（使用 `Pillow` 的 `ImageGrab`）
  3. 调用 RapidOCR 识别文字
  4. 在识别结果中根据鼠标相对位置定位最近单词
  5. 修改 `WordCapture.capture()` 逻辑：UI Automation 优先，返回空则尝试 OCR
- **验收**：在图片/PDF 等 UI Automation 无法取词的场景下，OCR 正确取到单词

---

### Task 10: 深色/浅色主题切换
- **目标**：弹窗支持跟随系统主题的深色/浅色两套配色
- **产出文件**：更新 `quickdict/styles/popup.qss`、更新 `quickdict/popup_widget.py`、更新 `quickdict/config.py`
- **步骤**：
  1. 编写两套 QSS：浅色（白底 #FFFFFF）和深色（深底 #1E1E2E）
  2. 使用 Windows 注册表 `AppsUseLightTheme` 检测系统当前主题
  3. 在 `config.py` 中增加主题配置项：auto / light / dark
  4. `PopupWidget` 初始化及主题变化时动态切换 QSS
- **验收**：切换 Windows 暗色模式后，弹窗自动跟随变化

---

### Task 11: 词形还原增强（Lemma 反查表）
- **目标**：提升变形词的查询命中率
- **产出文件**：更新 `quickdict/build_db.py`、更新 `quickdict/dict_engine.py`
- **步骤**：
  1. 在 `build_db.py` 中遍历所有词条的 `exchange` 字段
  2. 解析每个 `类型:变换词`，构建 `变换词 → 原形词` 的映射
  3. 特别关注 `0:lemma` 类型，同时也处理 `p/d/i/3/r/t/s` 等反向映射
  4. 将映射存入 SQLite 表 `lemma(variant TEXT, lemma TEXT)`，建立索引
  5. `DictEngine.lookup()` 第二步改为查询 `lemma` 表获取原形，再查主表
- **验收**：查询 "running" → 返回 "run"，查询 "better" → 返回 "good"

---

### Task 12: LRU 缓存 & 异步查询
- **目标**：避免重复查询，查询不阻塞 UI
- **产出文件**：更新 `quickdict/dict_engine.py`、更新 `quickdict/main.py`
- **步骤**：
  1. 在 `DictEngine` 中使用 `functools.lru_cache(maxsize=500)` 缓存 `lookup()` 结果
  2. 使用 `QThread` + 信号槽将查询放到后台线程
  3. 查询完成后通过 `pyqtSignal` 将结果发回 UI 线程
  4. 鼠标移动时引入 200ms 防抖定时器（`QTimer.singleShot`）
  5. 防抖期间单词变化则取消旧查询
- **验收**：快速移动鼠标不卡顿，相同单词第二次查询 <1ms

---

## P2 — 体验打磨

### Task 13: TTS 发音朗读
- **目标**：弹窗中点击发音按钮朗读单词
- **产出文件**：更新 `quickdict/popup_widget.py`、新增 `quickdict/tts.py`
- **步骤**：
  1. 使用 `pyttsx3` 初始化 TTS 引擎（Windows SAPI）
  2. 在弹窗单词行右侧增加 🔊 发音按钮
  3. 点击按钮调用 `tts.speak(word)`，在后台线程执行避免阻塞 UI
  4. 可选：设置语速、音量配置
- **验收**：点击发音按钮，扬声器朗读该单词

---

### Task 14: 查词历史 & 收藏生词本
- **目标**：记录查询历史，支持收藏单词
- **产出文件**：新增 `quickdict/history.py`、更新 `quickdict/popup_widget.py`
- **步骤**：
  1. 使用 SQLite 新建表 `history(id, word, timestamp)` 和 `favorites(id, word, timestamp)`
  2. 每次查询自动写入 `history` 表
  3. 弹窗中增加 ⭐ 收藏按钮，点击后存入 `favorites` 表
  4. 已收藏的单词显示实心 ★，再次点击取消收藏
  5. 在系统托盘菜单中增加"查词历史"入口，弹出单独窗口展示
  6. 历史窗口支持按时间排序、搜索过滤
- **验收**：收藏单词后在历史窗口中可看到；重启程序后数据仍在

---

### Task 15: PyInstaller 打包
- **目标**：打包为单文件 exe，方便分发
- **产出文件**：新增 `quickdict.spec`、`dist/QuickDict.exe`
- **步骤**：
  1. 编写 PyInstaller spec 文件，包含所有资源文件（icon、qss、db）
  2. 配置隐藏导入（pynput、uiautomation 等有隐式依赖）
  3. 设置应用图标、版本信息
  4. 测试打包后的 exe 功能完整性
  5. 可选：使用 Nuitka 替代以获得更好的性能和更小体积
- **验收**：双击 `QuickDict.exe` 可正常运行全部功能

---

## P3 — 远期扩展

### Task 16: 划词翻译模式
- **目标**：选中文本后自动弹出翻译
- **步骤**：
  1. 监听鼠标抬起事件，检测是否有文本被选中
  2. 读取系统剪贴板获取选中文本
  3. 判断是单词还是短语/句子，分别处理
  4. 单词走 `DictEngine`，句子走在线翻译 API

### Task 17: 全局搜索框
- **目标**：`Ctrl+Alt+S` 唤起独立搜索框，输入单词直接查词
- **步骤**：
  1. 创建无边框搜索窗口，类似 Spotlight / Alfred 样式
  2. 输入框支持实时联想（输入时调用 `match()` 显示候选词列表）
  3. 回车或点击候选词显示完整释义
  4. 注册全局快捷键 `Ctrl+Alt+S`

### Task 18: 生词本导出 Anki
- **目标**：将收藏的生词导出为 Anki 卡片
- **步骤**：
  1. 安装 `genanki` 库
  2. 设计卡片模板：正面为单词，反面为音标+中英释义
  3. 从 `favorites` 表读取所有收藏词
  4. 生成 `.apkg` 文件

---

## 任务依赖关系

```
Task 1 (脚手架)
  ├── Task 2 (数据库)  ── Task 3 (查询引擎) ─┐
  ├── Task 4 (快捷键)                         ├── Task 7 (集成联调)
  ├── Task 5 (取词)                            │      ├── Task 8 (托盘)
  └── Task 6 (弹窗 UI) ───────────────────────┘      ├── Task 9 (OCR)
                                                       ├── Task 10 (主题)
  Task 11 (Lemma) ── 依赖 Task 2, 3                   ├── Task 11 (Lemma)
  Task 12 (缓存)  ── 依赖 Task 3, 7                   └── Task 12 (缓存)
  
  Task 13 (发音)  ── 依赖 Task 6
  Task 14 (历史)  ── 依赖 Task 7
  Task 15 (打包)  ── 依赖全部 P0+P1
  
  Task 16-18      ── 依赖 Task 7
```

---

## 状态跟踪

| Task | 名称                   | 状态       | 备注 |
| ---- | ---------------------- | ---------- | ---- |
| 1    | 项目脚手架搭建         | ✅ 已完成  |      |
| 2    | CSV 导入 SQLite        | ⬜ 未开始  |      |
| 3    | 词典查询引擎           | ⬜ 未开始  |      |
| 4    | 全局快捷键监听         | ⬜ 未开始  |      |
| 5    | 屏幕取词 UI Automation | ⬜ 未开始  |      |
| 6    | 翻译弹窗 UI           | ⬜ 未开始  |      |
| 7    | 主程序集成联调         | ⬜ 未开始  |      |
| 8    | 系统托盘 & 后台常驻    | ⬜ 未开始  |      |
| 9    | OCR 备用取词           | ⬜ 未开始  |      |
| 10   | 深色/浅色主题          | ⬜ 未开始  |      |
| 11   | Lemma 反查表           | ⬜ 未开始  |      |
| 12   | LRU 缓存 & 异步查询    | ⬜ 未开始  |      |
| 13   | TTS 发音               | ⬜ 未开始  |      |
| 14   | 查词历史 & 生词本      | ⬜ 未开始  |      |
| 15   | PyInstaller 打包       | ⬜ 未开始  |      |
| 16   | 划词翻译               | ⬜ 未开始  |      |
| 17   | 全局搜索框             | ⬜ 未开始  |      |
| 18   | 生词本导出 Anki        | ⬜ 未开始  |      |
