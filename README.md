[简中文档](https://github.com/AClon314/jsonc-sdict/blob/main/README-zh_CN.md)

<div align="center">
<img src="https://raw.githubusercontent.com/AClon314/jsonc-sdict/refs/heads/main/logo.svg" alt="logo" width="128" height="128" />

# jsonc_sdict 即典

[![PyPI - Version](https://img.shields.io/pypi/v/jsonc-sdict)](https://pypi.org/project/jsonc-sdict/)

</div>

Round-trip comments for JSONC/HJSON, with dict-like APIs for config editing.

- Keep comments on read and write (`loads` → edit → `body` / `full`).
- Work with nested structures via `sdict` ≈ [deepmerge](https://github.com/toumorokoshi/deepmerge) + [deepdiff](https://github.com/seperman/deepdiff) + [benedict](https://github.com/fabiocaccamo/python-benedict)

> Comments are data too, just like codes are data too by John von Neumann

> [!WARNING]
> This project is currently `0.2.x` and still evolving.

## Install

```bash
pip install "jsonc-sdict[full]"
# pip install "jsonc-sdict[full] @ git+https://github.com/AClon314/jsonc-sdict.git"
```

For local development:

```bash
git clone https://github.com/AClon314/jsonc-sdict.git
cd jsonc-sdict
pip install -e ".[dev]"
```

## Usage

### jsonc

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

Use `CommentIn` to mark comment positions. See [test_jsonc.py](./test/test_jsonc.py).

- `CommentIn(left, right)` means a comment between two logical items.
- `CommentIn(key)` means comments attached to one pair's internal `k:` / `:v` / `v,` slots.

If you start from JSONC/HJSON text instead of a mapping, use `jsoncDict(raw, loads=hjson.loads, dumps=hjson.dumps)`.

#### Invalid JSONC examples

```jsonc
// /* this is still single-line comment
so this line is illegal */
```

```jsonc
/* // this is block comment */ trailing-text-is-illegal
```

### sdict

See [test_sdict.py](./test/test_sdict.py).

#### Common operations

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

### merge()

Based on [DeepDiff](https://zepworks.com/deepdiff/current/). See [Merge](#deep-Merge).

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

### deep-Merge

`merge((old, new))()` is the shortest form. For `list[dict]`, pass `dictDict=...` so items can be matched by an id-like key before diff/merge.

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

#### CLI merge

```bash
deep-merge -i '{a:{b:1}}' '{a:{b:2}}' -fo json -m new
# {"a": {"b": 2}}
```

### GetSetDel

See [test_get_set_del.py](./test/test_get_set_del.py).

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

## Develop

### env

`LOG=DEBUG` enables debug-level logging.

Common setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
LOG=DEBUG pytest -q
```

### Internal design

#### jsonc

- `jsoncDict.loads()` parses comments with tree-sitter and stores them into `comments`.
- `jsoncDict.body` renders the current value with comments restored.
- `jsoncDict.full` returns `header + body + footer`.
- `CommentIn(key)` comments are stored as slot maps, not raw strings, so key/colon/value/comma placement stays explicit.

#### sdict (common pitfalls)

- `sdict` wraps both mapping and iterable nodes; nested access may return `sdict` views, not raw dict/list.
- `jsoncDict` output depends on comment/data mutation paths; bypassing public APIs can leave internal state inconsistent.
- `dfs()` warns against mutating yielded data during iteration.
- `insert(update, key=...|index=...)` is ordering-oriented: it inserts by reordering keys after update.

#### weakList (common pitfalls)

- Items must support both `__hash__` and weak references (`__weakref__`); built-in `int/str/list/dict` do not qualify.
- Weak references can disappear when no strong references exist; list length can shrink unexpectedly.
- `WeakList(noRepeat=True)` is not identical to `OrderedWeakSet`: repeated append/insert can move item position.

## Related projects

### json loads()

| pypi                                                                                                                                                         | commits                                                                                                                                                                                                                                           | issues                                                                                                                                                                                                                     | about                                                               | comment                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| [spyoungtech/json-five ![⭐](https://img.shields.io/github/stars/spyoungtech/json-five?style=flat&label=⭐)](https://github.com/spyoungtech/json-five)       | [![🕒](https://img.shields.io/github/commit-activity/t/spyoungtech/json-five/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/spyoungtech/json-five/main?label=🕒)](https://github.com/spyoungtech/json-five/commits)           | [![🎯](https://img.shields.io/github/issues/spyoungtech/json-five?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/spyoungtech/json-five?label=❔)](https://github.com/spyoungtech/json-five/issues)       | Python JSON5 parser with **round-trip** preservation of comments    | can keep comment [in another API style](https://json-five.readthedocs.io/en/latest/comments.html) (e.g: `BlockComment`/`wsc_before`) |
| [tusharsadhwani/json5kit ![⭐](https://img.shields.io/github/stars/tusharsadhwani/json5kit?style=flat&label=⭐)](https://github.com/tusharsadhwani/json5kit) | [![🕒](https://img.shields.io/github/commit-activity/t/tusharsadhwani/json5kit/master?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/tusharsadhwani/json5kit/master?label=🕒)](https://github.com/tusharsadhwani/json5kit/commits) | [![🎯](https://img.shields.io/github/issues/tusharsadhwani/json5kit?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/tusharsadhwani/json5kit?label=❔)](https://github.com/tusharsadhwani/json5kit/issues) | A **Roundtrip** parser and CST for JSON, JSONC and JSON5.           |
| [dpranke/pyjson5 ![⭐](https://img.shields.io/github/stars/dpranke/pyjson5?style=flat&label=⭐)](https://github.com/dpranke/pyjson5)                         | [![🕒](https://img.shields.io/github/commit-activity/t/dpranke/pyjson5/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/dpranke/pyjson5/main?label=🕒)](https://github.com/dpranke/pyjson5/commits)                             | [![🎯](https://img.shields.io/github/issues/dpranke/pyjson5?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/dpranke/pyjson5?label=❔)](https://github.com/dpranke/pyjson5/issues)                         | A Python implementation of the JSON5 data format                    |
| [austinyu/ujson5 ![⭐](https://img.shields.io/github/stars/austinyu/ujson5?style=flat&label=⭐)](https://github.com/austinyu/ujson5)                         | [![🕒](https://img.shields.io/github/commit-activity/t/austinyu/ujson5/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/austinyu/ujson5/main?label=🕒)](https://github.com/austinyu/ujson5/commits)                             | [![🎯](https://img.shields.io/github/issues/austinyu/ujson5?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/austinyu/ujson5?label=❔)](https://github.com/austinyu/ujson5/issues)                         | A fast JSON5 encoder/decoder for Python                             |
| [qvecs/qjson5 ![⭐](https://img.shields.io/github/stars/qvecs/qjson5?style=flat&label=⭐)](https://github.com/qvecs/qjson5)                                  | [![🕒](https://img.shields.io/github/commit-activity/t/qvecs/qjson5/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/qvecs/qjson5/main?label=🕒)](https://github.com/qvecs/qjson5/commits)                                      | [![🎯](https://img.shields.io/github/issues/qvecs/qjson5?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/qvecs/qjson5?label=❔)](https://github.com/qvecs/qjson5/issues)                                  | 📎 A quick JSON5 implementation written in C, with Python bindings. |

### other format that support round-trip

- [python-poetry/tomlkit ![⭐](https://img.shields.io/github/stars/python-poetry/tomlkit?style=flat&label=⭐)](https://github.com/python-poetry/tomlkit) | [![🕒](https://img.shields.io/github/commit-activity/t/python-poetry/tomlkit/master?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/python-poetry/tomlkit/master?label=🕒)](https://github.com/python-poetry/tomlkit/commits) | [![🎯](https://img.shields.io/github/issues/python-poetry/tomlkit?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/python-poetry/tomlkit?label=❔)](https://github.com/python-poetry/tomlkit/issues)
- [ruamel.yaml](https://yaml.dev/doc/ruamel.yaml/example)
