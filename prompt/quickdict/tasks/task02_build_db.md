# Task 2: CSV 导入 SQLite 数据库 — 实现细节

## 目标
将 `ecdict.csv`（约 77 万词条）高效导入 SQLite 数据库，同时构建 lemma 反查表。

## 输入
- `ecdict.csv`：UTF-8 编码的 CSV 文件，首行为表头
- `stardict.py`：已有的 `StarDict` 类和 `DictCsv` 类

## 输出
- `quickdict/data/ecdict.db`：SQLite 数据库文件

## 实现要点

### 1. 数据库创建
```python
# 复用 StarDict 类创建空数据库
from stardict import StarDict
db = StarDict('quickdict/data/ecdict.db')
```

### 2. CSV 批量导入
- 使用 `DictCsv` 读取 CSV，或直接用 `csv.reader` 读取
- 不要逐条 commit，改为每 1000 条 commit 一次，大幅提升导入速度
- 导入时 `stardict.py` 的 `register()` 默认每条 commit，需传入 `commit=False` 并手动批量提交
- 显示进度：每 10000 条打印一次进度

### 3. Lemma 反查表
在 `ecdict.db` 中创建额外表：
```sql
CREATE TABLE IF NOT EXISTS lemma (
    variant TEXT NOT NULL,
    lemma TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lemma_variant ON lemma(variant);
```

解析逻辑：
```python
# exchange 字段格式: "d:perceived/p:perceived/3:perceives/i:perceiving"
# 同时也存在 "0:perceive" 表示当前词的原形是 perceive
for row in all_rows:
    word = row['word']
    exchange = row.get('exchange', '')
    if not exchange:
        continue
    for item in exchange.split('/'):
        if ':' not in item:
            continue
        typ, variant = item.split(':', 1)
        if typ == '0':
            # 当前词是变形，variant 是其原形
            # 记录: word -> variant (即 word 的原形是 variant)
            insert_lemma(word, variant)
        else:
            # variant 是 word 的某种变形
            # 记录: variant -> word (即 variant 的原形是 word)
            insert_lemma(variant, word)
```

### 4. 性能预估
- CSV 文件约 77 万行
- 批量提交（每 1000 条）预计导入时间：2-5 分钟
- lemma 表预计 200-300 万条映射记录

### 5. 注意事项
- CSV 中有些字段包含换行符（`\n`），`csv.reader` 可正确处理
- `detail` 字段为 JSON 字符串，需原样保存
- 首次运行生成 db 后，后续启动直接读取 db，无需重新导入
- 增加命令行参数 `--force` 支持强制重建
