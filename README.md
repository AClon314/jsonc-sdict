[简中文档](https://github.com/AClon314/jsonc-sdict/blob/main/README-zh_CN.md)

<div align="center">
<img src="https://raw.githubusercontent.com/AClon314/jsonc-sdict/refs/heads/main/logo.svg" alt="logo" width="128" height="128" />

# jsonc_sdict 即典

[![PyPI - Version](https://img.shields.io/pypi/v/jsonc-sdict)](https://pypi.org/project/jsonc-sdict/)

</div>

Round-trip comments for JSONC/HJSON, with dict-like APIs that stay simple & easy for app config editing.

- Keep comments on read and write (`loads` → edit → `restore`).
- Work with nested structures via `sdict` ≈ [deepmerge](https://github.com/toumorokoshi/deepmerge) + [deepdiff](https://github.com/seperman/deepdiff) + [benedict](https://github.com/fabiocaccamo/python-benedict)
- Use weak-reference ordered containers via `weakList`/`OrderedWeakSet`.

> Comments are data too, just like codes are data too by John von Neumann

> [!WARNING]
> This project is currently alpha (`0.1.x`) and still being refactored.

## Usage

### Install

```bash
pip install jsonc-sdict
```

For local development:

```bash
pip install -e ".[dev]"
```

### Quick start

```python
import json
import hjson
from jsonc_sdict import jsonc, AS_DATA

raw = """
// header
{
  "a": 1, // inline
  "b": 2
}
// footer
"""

def loads(self, obj):
    return hjson.loads(obj, ...) # pre-fill your custom args here

jc = jsoncDict(raw, loads, dumps=hjson.dumps)
jc.insert_comment(
    {
        "/*\\nnew-block": "multi\\nline\\n",
        "//\\nnew-line-above": "line above b\\n",
        "//this-is-data" + AS_DATA: ["not a comment key"],
    },
    key="b",
)

print(jc.full)
```

### Comment keyname rule

`jsonc` stores comments as synthetic keys in the underlying mapping:

```text
<prefix><position-marker><id><SEED>
```

- `SEED` is auto-appended to mark an internal comment key.
- Add `AS_DATA` suffix to force a key starting with comment prefix to be treated as normal data.

Common forms:

| Internal key prefix | Means                                    | Restored shape                                |
| ------------------- | ---------------------------------------- | --------------------------------------------- |
| `//`                | single-line comment, inline mode         | after current value/comma                     |
| `//\n`              | single-line comment, line-above mode     | independent line before next key/value        |
| `/*`                | block comment (default)                  | inline block comment                          |
| `/*\n`              | block comment with trailing newline mode | rendered with line break behavior             |
| `/*,`               | block comment before comma               | placed before comma of current item           |
| `/*k`               | block comment before key slot            | before JSON key token                         |
| `/*:`               | block comment before colon slot          | between key and value                         |
| `/*v`               | block comment before value slot          | after colon, before value                     |
| `/-`                | slash_dash comment                       | comments out a whole subtree (KDL-like style) |

Example mapping shape:

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
    "/-node<SEED>": {"ignored": "slash_dash comment"},
    "node": {"kept": "real data"},
}
```

### Edge cases

Invalid JSONC examples:

```jsonc
// /* this is still single-line comment
so this line is illegal */
```

```jsonc
/* // this is block comment */ trailing-text-is-illegal
```

## Develop

### env

`LOG=DEBUG` enables debug-level logging in project loggers.

Common setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
LOG=DEBUG pytest -q
```

### Internal design

#### jsonc

- Inline comment (`//...`): stored as `//<id><SEED>`, restored near the current item.
- Line-above comment (`//\n...`): stored as line-above mode, restored before next item.
- Block comment (`/*...*/`): stored with mode markers (`/*`, `/*,`, `/*k`, `/*:`, `/*v`, `/*\n`) to preserve placement.
- slash_dash comment (`/-name`): special key style that comments out a full subtree, similar to KDL config style.

#### sdict (common pitfalls)

- `sdict` wraps both mapping and iterable nodes; nested access may return `sdict` views, not raw dict/list.
- Cache fields (for example `body`, `body_restored`) rely on mutation hooks; bypassing APIs can leave stale cache.
- `dfs()` warns against mutating yielded data during iteration.
- `insert(update, key=...|index=...)` is ordering-oriented: it inserts by reordering keys after update.

#### weakList (common pitfalls)

- Items must support both `__hash__` and weak references (`__weakref__`); built-in `int/str/list/dict` do not qualify.
- Weak references can disappear when no strong references exist; list length can shrink unexpectedly.
- `WeakList(noRepeat=True)` is not identical to `OrderedWeakSet`: repeated append/insert can move item position.

## Related projects

### json loads()

| pypi                                                                                                                                                         | commits                                                                                                                                                                                                                                           | issues                                                                                                                                                                                                                     | about                                                               | lack                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [spyoungtech/json-five ![⭐](https://img.shields.io/github/stars/spyoungtech/json-five?style=flat&label=⭐)](https://github.com/spyoungtech/json-five)       | [![🕒](https://img.shields.io/github/commit-activity/t/spyoungtech/json-five/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/spyoungtech/json-five/main?label=🕒)](https://github.com/spyoungtech/json-five/commits)           | [![🎯](https://img.shields.io/github/issues/spyoungtech/json-five?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/spyoungtech/json-five?label=❔)](https://github.com/spyoungtech/json-five/issues)       | Python JSON5 parser with **round-trip** preservation of comments    | can keep comment, [but in AST-tree style with lots of re-defined concepts](https://json-five.readthedocs.io/en/latest/comments.html) (e.g: `BlockComment`/`wsc_before`) |
| [tusharsadhwani/json5kit ![⭐](https://img.shields.io/github/stars/tusharsadhwani/json5kit?style=flat&label=⭐)](https://github.com/tusharsadhwani/json5kit) | [![🕒](https://img.shields.io/github/commit-activity/t/tusharsadhwani/json5kit/master?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/tusharsadhwani/json5kit/master?label=🕒)](https://github.com/tusharsadhwani/json5kit/commits) | [![🎯](https://img.shields.io/github/issues/tusharsadhwani/json5kit?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/tusharsadhwani/json5kit?label=❔)](https://github.com/tusharsadhwani/json5kit/issues) | A **Roundtrip** parser and CST for JSON, JSONC and JSON5.           |
| [dpranke/pyjson5 ![⭐](https://img.shields.io/github/stars/dpranke/pyjson5?style=flat&label=⭐)](https://github.com/dpranke/pyjson5)                         | [![🕒](https://img.shields.io/github/commit-activity/t/dpranke/pyjson5/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/dpranke/pyjson5/main?label=🕒)](https://github.com/dpranke/pyjson5/commits)                             | [![🎯](https://img.shields.io/github/issues/dpranke/pyjson5?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/dpranke/pyjson5?label=❔)](https://github.com/dpranke/pyjson5/issues)                         | A Python implementation of the JSON5 data format                    |
| [austinyu/ujson5 ![⭐](https://img.shields.io/github/stars/austinyu/ujson5?style=flat&label=⭐)](https://github.com/austinyu/ujson5)                         | [![🕒](https://img.shields.io/github/commit-activity/t/austinyu/ujson5/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/austinyu/ujson5/main?label=🕒)](https://github.com/austinyu/ujson5/commits)                             | [![🎯](https://img.shields.io/github/issues/austinyu/ujson5?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/austinyu/ujson5?label=❔)](https://github.com/austinyu/ujson5/issues)                         | A fast JSON5 encoder/decoder for Python                             |
| [qvecs/qjson5 ![⭐](https://img.shields.io/github/stars/qvecs/qjson5?style=flat&label=⭐)](https://github.com/qvecs/qjson5)                                  | [![🕒](https://img.shields.io/github/commit-activity/t/qvecs/qjson5/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/qvecs/qjson5/main?label=🕒)](https://github.com/qvecs/qjson5/commits)                                      | [![🎯](https://img.shields.io/github/issues/qvecs/qjson5?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/qvecs/qjson5?label=❔)](https://github.com/qvecs/qjson5/issues)                                  | 📎 A quick JSON5 implementation written in C, with Python bindings. |

### other format that support round-trip

- [python-poetry/tomlkit ![⭐](https://img.shields.io/github/stars/python-poetry/tomlkit?style=flat&label=⭐)](https://github.com/python-poetry/tomlkit) | [![🕒](https://img.shields.io/github/commit-activity/t/python-poetry/tomlkit/master?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/python-poetry/tomlkit/master?label=🕒)](https://github.com/python-poetry/tomlkit/commits) | [![🎯](https://img.shields.io/github/issues/python-poetry/tomlkit?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/python-poetry/tomlkit?label=❔)](https://github.com/python-poetry/tomlkit/issues)
- [ruamel.yaml](https://yaml.dev/doc/ruamel.yaml/example)
