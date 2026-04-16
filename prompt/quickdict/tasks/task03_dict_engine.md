# Task 3: 词典查询引擎 — 实现细节

## 目标
封装统一的词典查询接口，支持多级回退查询和结果格式化。

## 类设计

```python
class DictEngine:
    def __init__(self, db_path: str)
    def lookup(self, word: str) -> dict | None
    def match_candidates(self, word: str, limit: int = 5) -> list[str]
    def close(self)
```

## 查询策略（lookup 方法）

```
输入 word
  │
  ├─① 精确查询：SELECT * FROM stardict WHERE word = ? (NOCASE)
  │   └─ 命中 → 返回结果
  │
  ├─② Lemma 反查：SELECT lemma FROM lemma WHERE variant = ?
  │   └─ 找到原形 → 用原形重新查 stardict → 返回结果（附带标注 "原形: xxx"）
  │
  ├─③ Strip 模糊查询：stripword(word) 后查 sw 字段
  │   └─ 命中 → 返回结果
  │
  └─④ 前缀匹配：StarDict.match(word, limit=5)
      └─ 返回候选词列表（供 UI 展示）
```

## 结果格式化

`lookup()` 返回的字典格式：
```python
{
    "word": "perceive",
    "phonetic": "/pəˈsiːv/",
    "translation": "vt. 察觉，感觉；理解；认知",
    "definition": "v. to become aware of through the senses",
    "collins_stars": 3,          # 整数 0-5
    "collins_display": "★★★☆☆",  # 格式化后的星级
    "oxford": True,              # 是否牛津核心词汇
    "bnc": 3218,
    "frq": 2856,
    "tags": ["cet6", "gre", "ielts"],  # 解析 tag 字段
    "tag_display": "六级 GRE 雅思",      # 中文标签
    "exchange": {
        "p": "perceived",        # 过去式
        "d": "perceived",        # 过去分词
        "i": "perceiving",       # 现在分词
        "3": "perceives",        # 第三人称单数
    },
    "is_lemma_result": False,    # 是否通过词形还原查到的
    "original_word": None,       # 如果是词形还原，这里是用户输入的原词
}
```

## Tag 标签映射表
```python
TAG_MAP = {
    "zk": "中考",
    "gk": "高考",
    "cet4": "四级",
    "cet6": "六级",
    "ky": "考研",
    "toefl": "托福",
    "ielts": "雅思",
    "gre": "GRE",
}
```

## Exchange 类型映射表
```python
EXCHANGE_MAP = {
    "p": "过去式",
    "d": "过去分词",
    "i": "现在分词",
    "3": "第三人称单数",
    "r": "比较级",
    "t": "最高级",
    "s": "复数",
    "0": "原形",
    "1": "原形变换类型",
}
```

## 注意事项
- SQLite 连接在 `__init__` 中创建，在 `close()` 中关闭，整个生命周期复用
- `lookup()` 结果后续可被 LRU 缓存（Task 12）
- translation / definition 字段中的 `\n` 表示多条释义，前端需要逐行展示
- collins 字段可能为 0 或 NULL，均视为无星级
