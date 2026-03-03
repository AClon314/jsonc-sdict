# jsonc_sdict 即典

Doc: [English](./README.md)

支持 JSONC/HJSON 的注释保留工具，提供实用、直接的字典式 API，适合配置文件编辑场景。

- 读写都保留注释（`bake` → 修改 → `restore`）。
- 通过 `sdict` 处理嵌套结构更方便，等价于 [deepmerge](https://github.com/toumorokoshi/deepmerge) + [deepdiff](https://github.com/seperman/deepdiff) + [benedict](https://github.com/fabiocaccamo/python-benedict)
- 提供弱引用有序容器 `weakList` / `OrderedWeakSet`。

> [!WARNING]
> 项目当前仍处于 alpha（`0.1.x`）阶段，正在持续重构。

## 用法

### 安装

```bash
pip install jsonc_sdict
```

本地开发安装：

```bash
pip install -e ".[dev]"
```

### 快速开始

```python
import json
from jsonc_sdict import jsonc
from jsonc_sdict.jsonc import AS_DATA

raw = """
// header
{
  "a": 1, // inline
  "b": 2
}
// footer
"""

jc = jsonc()
body = jc.bake(raw)         # 将注释提取为 comment-key
jc.update(json.loads(body)) # 用普通 JSON 解析结果回填

jc.insert_comment(
    {
        "/*\\nnew-block": "multi\\nline\\n",
        "//\\nnew-line-above": "line above b\\n",
        "//this-is-data" + AS_DATA: ["not a comment key"],
    },
    key="b",
)

out = jc.full
print(out)
```

### comment keyname 规则

`jsonc` 会把注释存成底层映射里的“合成键”：

```text
<prefix><position-marker><id><SEED>
```

- `SEED`：自动追加，用来标记这是内部注释键。
- `AS_DATA`：若业务键名本身以注释前缀开头，可在末尾加 `AS_DATA`，强制按普通数据键处理。

常见前缀语义：

| 内部键前缀 | 含义 | 还原后位置 |
| --- | --- | --- |
| `//` | 单行注释，行内模式 | 放在当前值/逗号附近 |
| `//\n` | 单行注释，行上模式 | 放在下一个 key/value 前独立成行 |
| `/*` | 多行注释（默认） | 行内块注释 |
| `/*\n` | 多行注释 + 换行模式 | 按换行语义还原 |
| `/*,` | 逗号前多行注释 | 放在当前项逗号前 |
| `/*k` | key 槽位前多行注释 | 放在 JSON key 前 |
| `/*:` | 冒号槽位前多行注释 | 放在 key 和 value 之间 |
| `/*v` | value 槽位前多行注释 | 放在冒号后、value 前 |
| `/-` | 节点注释 | 注释整棵子树（类似 KDL 风格） |

内部结构示例：

```python
{
    "//0<SEED>": ' "": null,',
    "0": 0,
    "//1<SEED>": " 0",
    "//\n2<SEED>": ' "1": 1,/* 1 */',
    "/*,3<SEED>": " 2 ",
    "2": 2,
    "/*\n4<SEED>": " 👻 ",
    "/*v6<SEED>": " 6 ",
    "6//": 6,
    "/*k7<SEED>": " 7 ",
    "7": 7,
    "/-node<SEED>": {"ignored": "node comment"},
    "node": {"kept": "real data"},
}
```

### 边界情况

以下 JSONC 写法非法：

```jsonc
// /* 这依然是单行注释
所以这一行是非法的 */
```

```jsonc
/* // 这是多行注释 */ trailing-text-is-illegal
```

## Develop

### env

`LOG=DEBUG` 会把项目 logger 打到 debug 级别。

常用开发流程：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
LOG=DEBUG pytest -q
```

### 内部原理

#### jsonc

注释也是数据

- 行内注释（`//...`）
  - what：注释附着在当前数据项行内。
  - how：内部键为 `//<id><SEED>`，还原时放在当前项附近。
- 行上注释（`//\n...`）
  - what：注释独立成行，位于下一个数据项上方。
  - how：内部键用 `//\n` 模式；还原时优先进入 line-above 队列。
- 多行注释（`/*...*/`）
  - what：支持放在 key 前、冒号前、value 前、逗号前、或行间。
  - how：通过 `/*`、`/*,`、`/*k`、`/*:`、`/*v`、`/*\n` 等标记编码具体槽位。
- 节点注释（`/-node`）
  - what：注释整棵子树，不参与正常数据输出。
  - how：使用 `/-` 前缀识别，行为类似 KDL 的节点注释风格。

#### sdict（易混淆点/坑）

- `sdict` 会包装映射和可迭代节点；嵌套读取时常拿到 `sdict` 视图而不是原始 dict/list。
- 缓存字段（例如 `body`、`body_restored`）依赖标准 mutation 路径；绕开 API 修改底层对象可能导致缓存过期。
- `dfs()` 迭代期间不建议直接改动正在遍历的数据。
- `insert(update, key=...|index=...)` 的核心是“更新后重排顺序”，不是简单 append。

#### weakList（易混淆点/坑）

- 元素必须同时支持 `__hash__` 与弱引用（`__weakref__`）；`int/str/list/dict` 这类内建类型不行。
- 若没有强引用，弱引用对象可能被回收，`WeakList` 长度会“自动变短”。
- `WeakList(noRepeat=True)` 不等同 `OrderedWeakSet`：重复 append/insert 会触发位置移动语义。

## 相关项目

可参考的 JSON/JSONC/JSON5 解析项目：

- `spyoungtech/json-five`
- `tusharsadhwani/json5kit`
- `dpranke/pyjson5`
- `austinyu/ujson5`
- `qvecs/qjson5`

其他支持 round-trip 的格式工具：

- `python-poetry/tomlkit`
- `ruamel.yaml`
