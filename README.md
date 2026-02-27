# jsonc_sdict 即典

- jsonc, maybe is the only solution that keep comments(round trip) as data.
- sdict = [deepmerge](https://github.com/toumorokoshi/deepmerge) + [deepdiff](https://github.com/seperman/deepdiff) + [benedict](https://github.com/fabiocaccamo/python-benedict)

## inner principle

- treated comments like actual data by `bake()`: `"//0": "my comment"`, `"/*0": "my\ncomment"`
- depend on `deepdiff` to merge old and new into one with comments
- a new `jdict` class like the logic of [benedict](https://github.com/fabiocaccamo/python-benedict) to visit nested dict by `dict[[keyA, keyAA, ...]]`
- you need other package/lib's `load`/`loads`, which also gives your freedom to choose the load/dump engine

## Usage

```python
{
    '//0<SEED>': ' "": null, # dict内的顺序与真实的注释出现位置一致
    '0': 0,
    '//1<SEED>': ' 0', # 行内注释，在dict内的排序需要在真实数据的后面。
    '//2<SEED>': ' "1": 1,/* 1 */\n', # 行上注释，则末尾应该有个\n
    '/*,3<SEED>': ' 2 ', # 不应为`/*`，而应为`/*,`，其中prefix[0:1]=="/*"，而prefix[2]==","代表这个多行注释应该`放到一个逗号前面`的意思; 多行注释按`向下查找的栈`规则，所以需要放到真实数据 "2": 2的前面。
    '2': 2,
    '/*\n4<SEED>': ' 👻 ', # `/*\n`代表多行注释的末尾是一个换行符，也相当于多行版本的行上注释
    '/*,5<SEED>': ' 3\n  4\n  * 5\n  ', # 不应为`/*`，而应为`/*,`
    '3': 3,
    '/*v6<SEED>': ' 6 ', # `/*v` 代表多行注释应该出现在实际的value槽位之前
    '6//': 6,
    '/*k7<SEED>': ' 7 ', # `/*k` 代表多行注释应该出现在实际的key槽位之前
    '7': 7,
    '/*\n8<SEED>': ' 8 ', # `/*\n`代表多行注释应该在**下方**kv数据的末尾，然后是换行符(这一点不要与 "//...": "...\n"行上注释末尾必须是\n 的规则混淆了)
    '8': 8,
    '//9<SEED>': ' "9": 9',
    '/-node<SEED>': jsonc({'just ignore these': 'i am in node comment'}),
    'node': jsonc({'do not ignore me': 'i am real data!'}),
}
```

同理，`/*:`代表多行注释应该出现在冒号前面，key槽位的后面。

## json5 loads() substitute

| pypi                                                                                                                                                         | commits                                                                                                                                                                                                                                           | issues                                                                                                                                                                                                                     | about                                                               | lack                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [spyoungtech/json-five ![⭐](https://img.shields.io/github/stars/spyoungtech/json-five?style=flat&label=⭐)](https://github.com/spyoungtech/json-five)       | [![🕒](https://img.shields.io/github/commit-activity/t/spyoungtech/json-five/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/spyoungtech/json-five/main?label=🕒)](https://github.com/spyoungtech/json-five/commits)           | [![🎯](https://img.shields.io/github/issues/spyoungtech/json-five?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/spyoungtech/json-five?label=❔)](https://github.com/spyoungtech/json-five/issues)       | Python JSON5 parser with **round-trip** preservation of comments    | can keep comment, [but in AST-tree style with lots of re-defined concepts](https://json-five.readthedocs.io/en/latest/comments.html) (e.g: `BlockComment`/`wsc_before`) |
| [tusharsadhwani/json5kit ![⭐](https://img.shields.io/github/stars/tusharsadhwani/json5kit?style=flat&label=⭐)](https://github.com/tusharsadhwani/json5kit) | [![🕒](https://img.shields.io/github/commit-activity/t/tusharsadhwani/json5kit/master?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/tusharsadhwani/json5kit/master?label=🕒)](https://github.com/tusharsadhwani/json5kit/commits) | [![🎯](https://img.shields.io/github/issues/tusharsadhwani/json5kit?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/tusharsadhwani/json5kit?label=❔)](https://github.com/tusharsadhwani/json5kit/issues) | A **Roundtrip** parser and CST for JSON, JSONC and JSON5.           |
| [dpranke/pyjson5 ![⭐](https://img.shields.io/github/stars/dpranke/pyjson5?style=flat&label=⭐)](https://github.com/dpranke/pyjson5)                         | [![🕒](https://img.shields.io/github/commit-activity/t/dpranke/pyjson5/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/dpranke/pyjson5/main?label=🕒)](https://github.com/dpranke/pyjson5/commits)                             | [![🎯](https://img.shields.io/github/issues/dpranke/pyjson5?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/dpranke/pyjson5?label=❔)](https://github.com/dpranke/pyjson5/issues)                         | A Python implementation of the JSON5 data format                    |
| [austinyu/ujson5 ![⭐](https://img.shields.io/github/stars/austinyu/ujson5?style=flat&label=⭐)](https://github.com/austinyu/ujson5)                         | [![🕒](https://img.shields.io/github/commit-activity/t/austinyu/ujson5/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/austinyu/ujson5/main?label=🕒)](https://github.com/austinyu/ujson5/commits)                             | [![🎯](https://img.shields.io/github/issues/austinyu/ujson5?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/austinyu/ujson5?label=❔)](https://github.com/austinyu/ujson5/issues)                         | A fast JSON5 encoder/decoder for Python                             |
| [qvecs/qjson5 ![⭐](https://img.shields.io/github/stars/qvecs/qjson5?style=flat&label=⭐)](https://github.com/qvecs/qjson5)                                  | [![🕒](https://img.shields.io/github/commit-activity/t/qvecs/qjson5/main?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/qvecs/qjson5/main?label=🕒)](https://github.com/qvecs/qjson5/commits)                                      | [![🎯](https://img.shields.io/github/issues/qvecs/qjson5?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/qvecs/qjson5?label=❔)](https://github.com/qvecs/qjson5/issues)                                  | 📎 A quick JSON5 implementation written in C, with Python bindings. |

## other format that support round-trip

- [python-poetry/tomlkit ![⭐](https://img.shields.io/github/stars/python-poetry/tomlkit?style=flat&label=⭐)](https://github.com/python-poetry/tomlkit) | [![🕒](https://img.shields.io/github/commit-activity/t/python-poetry/tomlkit/master?label=🕒) ![LAST🕒](https://img.shields.io/github/last-commit/python-poetry/tomlkit/master?label=🕒)](https://github.com/python-poetry/tomlkit/commits) | [![🎯](https://img.shields.io/github/issues/python-poetry/tomlkit?label=⁉️) ![🎯close](https://img.shields.io/github/issues-closed/python-poetry/tomlkit?label=❔)](https://github.com/python-poetry/tomlkit/issues)
- [ruamel.yaml](https://yaml.dev/doc/ruamel.yaml/example)
