[English](./README.md)

<div align="center">
<img src="https://raw.githubusercontent.com/AClon314/jsonc-sdict/refs/heads/main/logo.svg" alt="logo" width="128" height="128" />

# jsonc_sdict 即典

[![PyPI - Version](https://img.shields.io/pypi/v/jsonc-sdict)](https://pypi.org/project/jsonc-sdict/)

</div>

支持 JSONC/HJSON 的注释保留工具，提供直接的字典式 API，适合配置文件编辑场景。

- 读写都保留注释（`loads` → 修改 → `body` / `full`）。
- 通过 `sdict` 处理嵌套结构更方便，等价于 [deepmerge](https://github.com/toumorokoshi/deepmerge) + [deepdiff](https://github.com/seperman/deepdiff) + [benedict](https://github.com/fabiocaccamo/python-benedict)

> 注释也是数据，就如冯・诺依曼，代码也是数据

> [!WARNING]
> 项目当前为 `0.2.x`，仍在持续演进。

## 安装

```bash
pip install "jsonc-sdict[full]"
# pip install "jsonc-sdict[full] @ git+https://github.com/AClon314/jsonc-sdict.git"
```

本地开发安装：

```bash
git clone https://github.com/AClon314/jsonc-sdict.git
cd jsonc-sdict
pip install -e ".[dev]"
```

## 用法

### jsonc

用 `CommentIn` 标记注释位置，见 [test_jsonc.py](./test/test_jsonc.py)：

```python
from jsonc_sdict import jsoncDict, CommentIn, NONE

jc = jsoncDict(
    {
        CommentIn(NONE, "a"): "// before a",
        "a": 1,
        CommentIn("a", "b"): "// between a and b",
        "b": 2,
    }
)
jc[CommentIn("b")] = {CommentIn(":", "v"): "/* before value */"}
jc["b"] = 3

print(jc.full)
```

- `CommentIn(left, right)` 表示两个逻辑项之间的注释。
- `CommentIn(key)` 表示单个键值对内部 `k:` / `:v` / `v,` 槽位上的注释。

如果输入是 JSONC/HJSON 文本而不是映射对象，用 `jsoncDict(raw, loads=hjson.loads, dumps=hjson.dumps)`。

#### 非法 JSONC 示例

```jsonc
// /* 这依然是单行注释
所以这一行是非法的 */
```

```jsonc
/* // 这是多行注释 */ trailing-text-is-illegal
```

### sdict

见 [test_sdict.py](./test/test_sdict.py)。

#### 常用操作

```python
from jsonc_sdict import sdict

data = sdict({"node": {"items": [0, {"value": 1}]}, "a": 1, "b": 2, "c": 2})

print(data["node", "items", 1, "value"])
data["node", "items", 1, "value"] = 2

node = data["node"]
print(node.keypath)
print(node.parent is data)

data.insert({"x": 9}, key="a", after=True)
data.rename_key("x", "y")
data.sort(reverse=True)

print(list(data.items()))
print(data.unref())
```

### 合并merge()

基于 [DeepDiff](https://zepworks.com/deepdiff/current/)，详见 [Merge](#merge)。

```python
from functools import partial
from jsonc_sdict import get1, merge

old = {"children": [{"id": 1, "name": "1", "old": None}]}
new = {"children": [{"id": 1, "name": "2", "new": ""}, {"id": 2, "name": "3"}]}

result = merge(
    (old, new),
    dictDict={"value_of_idKey": partial(get1.item, keys="id")},
    unMergeable="new",
)()

print(result)
```

### Merge

最短写法是 `merge((old, new))()`。如果是 `list[dict]`，通常要传 `dictDict=...`，先按 id 之类的键做匹配，再进行 diff / merge。

```python
from functools import partial
from jsonc_sdict import get1, merge

old = {"items": [{"id": 1, "name": "old", "keep": True}]}
new = {"items": [{"id": 1, "name": "new"}, {"id": 2, "name": "add"}]}

merged = merge(
    (old, new),
    dictDict={"value_of_idKey": partial(get1.item, keys="id")},
    unMergeable="new",
)()

print(merged)
```

#### CLI 命令行合并

```bash
deep-merge -i '{a:{b:1}}' '{a:{b:2}}' -fo json -m new
# {"a": {"b": 2}}
```

### GetSetDel

见 [test_get_set_del.py](./test/test_get_set_del.py)：

```python
from jsonc_sdict import get1, set1
from jsonc_sdict.GetSetDel import del1

obj = {"a": {"b": 1}}

print(get1.item(obj, ("a", "b")))
print(set1.item(obj, ("a", "b"), 2))
print(set1.item(obj, ("a", "c"), 3))
del1.item(obj, ("a", "b"))

print(obj)
```

## 开发&调试

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

- `jsoncDict.loads()` 使用 tree-sitter 解析并把注释写入 `comments`。
- `jsoncDict.body` 把注释回填到序列化结果。
- `jsoncDict.full` 等于 `header + body + footer`。
- `CommentIn(key)` 不再存原始字符串，而是存槽位字典，便于精确恢复 `k:`、`:v`、`v,`。

#### sdict（易混淆点/坑）

- `sdict` 会包装映射和可迭代节点；嵌套读取时常拿到 `sdict` 视图而不是原始 dict/list。
- `jsoncDict` 的输出依赖标准的数据/注释修改路径；绕开公开 API 修改底层对象可能导致内部状态不一致。
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

## 题外话

### 保留注释的双向读写

在开发本包的时候，刷到了这位老哥的评论：“[其中很少有人需要这个](https://github.com/toml-lang/toml/issues/836#issuecomment-1476585718)”

我觉得这个功能就是，只要有人做出来，就会有很多人会用。

### 痛苦的依赖开发

- WeakList: 因为动态语言有GC，**子**引用**父**必须是弱引用，考虑到有多个父的极端情况，自制了一个WeakList/OrderedWeakSet
- merge: DeepDiff不支持合并
- dictDict: list[dict]很难合并，而dict很好合并，需要让用户主动选择一个idKey，来方便确定list[dict]内的old_dict,new_dict之间的对应关系
- sdict: 注释在数据中的顺序很重要，继承了OrderedDict重写了纯python的实现。
  且因可能存在很深层的数据结构，需要一个方便访问深层结构的api，故参考了benedict(benedict写死了用str做键名)，从头重写了大部分逻辑来解除这个限制。

### 类似DeepDiff的库

#### JavaScript / TypeScript

- **microdiff** (https://github.com/AsyncBanana/microdiff)  
  极快、零依赖、现代实现（比 deep-diff 快很多）。  
  Stars: ~1.5k–2k+  
  最后更新: 近期活跃（2024-2025仍有更新）  
  Open issues: 较少（10-20个左右）

- **just-diff** / **deep-object-diff** 等也类似，但 microdiff 和 deep-diff 是最直接的竞品。

#### Java

- **javers** (https://github.com/javers/javers)  
  最成熟、最接近 DeepDiff 的 Java 库，支持任意对象图的深度 diff、变更追踪、快照等，企业级常用。  
  Stars: ~3.5k–4k+  
  最后更新: 非常活跃（2025-2026仍在频繁提交）  
  Open issues: 几十到上百（项目较大）

- **java-object-diff** (https://github.com/SQiShER/java-object-diff)  
  专注于对象深度差异。  
  Stars: ~1k 左右  
  最后更新: 几年前（基本稳定）  
  Open issues: 较少

#### ~~Go (Golang)~~

- **qri-io/deepdiff** (https://github.com/qri-io/deepdiff)  
  结构化数据深度 diff，目标是近线性时间复杂度。  
  Stars: 几百（不算特别高）  
  最后更新: 2021-2023 左右（维护较少）  
  Open issues: 少量

Go 语言中**没有**特别火的“DeepDiff 等价物”，很多项目自己实现或用 reflect 简单比较。

#### Rust

- **turbodiff** (https://github.com/BrightNight-Energy/turbodiff)  
  明确标榜为 Rust 版的 fast deepdiff，速度优先。  
  Stars: 几百（新兴）  
  最后更新: 近期（2024-2025活跃）  
  Open issues: 很少

Rust 社区更倾向使用 serde + 自定义 diff，或类似工具，但 turbodiff 是最接近的。

#### 其他语言补充

- **Clojure** → **lambdaisland/deep-diff2** (https://github.com/lambdaisland/deep-diff2)  
  Stars: ~几百  
  最后更新: 活跃  
  非常适合 Clojure 数据结构。

- **Swift** → **DeepDiff** (https://github.com/onmyway133/DeepDiff)  
  同名但不同库，iOS/macOS 常用。  
  Stars: ~2k+  
  最后更新: 活跃

- **Julia** → **DeepDiffs.jl** (较小众)

### v0.3 TODO 新功能

- [ ] 自动处理CommentIn冲突，目前v0.2手动处理。insert/rename/sort/delete 时的注释迁移规则，以及 inline comment 的列对齐策略。insert comments CommentIn(...) solve conflict?
- [ ] 追踪&备份配置文件(yadm git for linux, fallback rename&copy for windows)
- [ ] 字符串类git合并(str merge based on fast-diff-match-patch)
- [ ] pydantic docstring 自动插入为注释
- [ ] jmespath 兼容性? ~~jsonpath~~
