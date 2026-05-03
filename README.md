[简中文档](https://github.com/AClon314/jsonc-sdict/blob/main/README-zh_CN.md)

<div align="center">
<img src="https://raw.githubusercontent.com/AClon314/jsonc-sdict/refs/heads/main/logo.svg" alt="logo" width="128" height="128" />

# jsonc_sdict 即典

[![PyPI - Version](https://img.shields.io/pypi/v/jsonc-sdict)](https://pypi.org/project/jsonc-sdict/)

</div>

Round-trip comments for JSONC/HJSON, with dict-like APIs for config editing.

- Keep comments on read and write (`loads` → edit → `body` / `full`).
- Work with nested structures via `sdict` ≈ [deepmerge](https://github.com/toumorokoshi/deepmerge) + [deepdiff](https://github.com/seperman/deepdiff) + [benedict](https://github.com/fabiocaccamo/python-benedict)
- Use weak-reference ordered containers via `weakList`/`OrderedWeakSet`.

> Comments are data too, just like codes are data too by John von Neumann

> [!WARNING]
> This project is currently `0.2.x` and still evolving.

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
import hjson
from jsonc_sdict import jsoncDict, Within, NONE

raw = """
// header
{
  "a": 1, // inline
  "b": 2
}
// footer
"""

jc = jsoncDict(raw, loads=hjson.loads, dumps=hjson.dumps)
jc.comments[Within(NONE, "a")] = "// before a"
jc.comments[Within("a")] = {
    Within("k", ":"): "/* key slot */",
    Within(":", "v"): "/* value slot */",
    Within("v", ","): "/* tail slot */",
}

print(jc.body)
print(jc.full)
```

### Comment model

`jsoncDict.comments` stores comment positions with `Within(...)` keys.

- `Within(left, right)` means a comment between two logical items.
- `Within(key)` means comments attached to one pair's internal slots.
- Slot comments use a dict with `Within("k", ":")`, `Within(":", "v")`, `Within("v", ",")`.
- `Within(NONE, first_key)` and `Within(last_key, NONE)` handle boundary comments.

Examples:

```python
jc.comments[Within("a", "b")] = "// between a and b"
jc.comments[Within("b")] = {
    Within("k", ":"): "/* before colon */",
    Within(":", "v"): "/* before value */",
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

- `jsoncDict.loads()` parses comments with tree-sitter and stores them into `comments`.
- `jsoncDict.body` renders the current value with comments restored.
- `jsoncDict.full` returns `header + body + footer`.
- `Within(key)` comments are stored as slot maps, not raw strings, so key/colon/value/comma placement stays explicit.

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
