# LinguaLens Fork of ECDICT

这个仓库是基于 ECDICT 的二次开发版本，当前主线集成了三套可运行的 Windows 桌面工具：

- QuickDict：基于 OCR + ECDICT 数据库的屏幕取词和词典查询
- MagicMirror：基于 OCR + LLM 的屏幕区域翻译覆盖层
- LinguaLens：把 QuickDict 和 MagicMirror 合并到一个统一托盘入口

原始 ECDICT 相关脚本与资料已整理到 ecdict 目录，便于与新功能代码隔离。

## Repository Layout

- quickdict: QuickDict 应用源码
- magic_mirror: MagicMirror 应用源码
- lingualens_main.py: LinguaLens 统一入口
- ecdict: 原始 ECDICT 脚本与资料（已归档）
- stardict: 词典 CSV 数据源
- data: 运行期数据库与用户配置
- quickdict.spec / magicmirror.spec / lingualens.spec: 三个 PyInstaller 打包配置
- build_release_quickdict.bat / build_release_magicmirror.bat / build_release_lingualens.bat: 三个发布脚本

## Applications

### 1) QuickDict

定位：本地词典查词（速度优先，离线可用）

主要能力：

- 全局热键触发取词
- UI Automation + OCR 混合取词
- 多级查询回退（精确、lemma、模糊）
- 系统托盘常驻

开发启动：

1. 运行 setup.bat（创建虚拟环境、安装依赖、构建数据库）
2. 执行 .venv\Scripts\python -m quickdict.main

发布打包：

- 执行 build_release_quickdict.bat

说明：QuickDict 发布时会把程序与大体积数据库分离，数据库文件为 data\ecdict.db。

### 2) MagicMirror

定位：屏幕区域实时翻译（OCR + LLM）

主要能力：

- 区域截图 + OCR 文本提取
- 基于 OpenAI 兼容接口的翻译
- 覆盖层显示、右键菜单交互
- 热键触发翻译与纯 OCR 提取

开发启动：

1. 安装依赖：.venv\Scripts\pip install -r magic_mirror\requirements.txt
2. 配置 magic_mirror\config\llm_providers.yaml 与 .env
3. 执行 .venv\Scripts\python -m magic_mirror.main

发布打包：

- 执行 build_release_magicmirror.bat

说明：发布包只包含 .example 配置模板，用户需要重命名并填写真实配置。

### 3) LinguaLens

定位：QuickDict + MagicMirror 合体应用（统一托盘）

主要能力：

- 同时加载查词与翻译两套功能
- 统一托盘菜单控制
- 在 MagicMirror 配置缺失时降级为仅 QuickDict 可用

开发启动：

- 执行 .venv\Scripts\python lingualens_main.py

发布打包：

- 执行 build_release_lingualens.bat

## Setup Notes

### Python Environment

建议使用仓库根目录的 .venv。

QuickDict 的 setup.bat 会自动：

- 创建 .venv
- 安装 quickdict\requirements.txt
- 构建 data\ecdict.db

如果要运行 MagicMirror 或 LinguaLens，还需要额外安装：

- magic_mirror\requirements.txt

### Database Source

QuickDict 构建数据库时默认读取：

- stardict\stardict.csv

构建产物：

- data\ecdict.db

## Build Scripts (Windows)

- build_release_quickdict.bat: 生成 QuickDict 发布目录
- build_release_magicmirror.bat: 生成 MagicMirror 发布目录
- build_release_lingualens.bat: 生成 LinguaLens 发布目录

当前 QuickDict 发布脚本已增强以下稳定性处理：

- 自动尝试结束 QuickDict.exe / LinguaLens.exe，减少文件占用冲突
- 清理旧发布目录失败时可回退到时间戳目录
- 关键复制步骤失败时立即退出，避免“假成功”

## Original ECDICT Content

原始仓库内容已归档到 ecdict 目录，例如：

- ecdict\stardict.py
- ecdict\dictutils.py
- ecdict\linguist.py
- ecdict\README.md

新增的 quickdict / magic_mirror / lingualens 主线与原始资料分区管理，便于后续持续开发与发布。

## License

沿用仓库根目录 LICENSE。