#!/bin/env python3
"""
```
"""

import re
import json
from uuid import uuid4
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
    Iterable,
    MutableSequence,
)
from typing import Any, TypeIs, Unpack, Literal, cast, Self

import tree_sitter as ts
import tree_sitter_json as ts_json

from jsonc_sdict.share import (
    UNSET,
    RegexPattern,
    getLogger,
    iterable,
    args_of_type,
    _TODO,
)
from jsonc_sdict.Sdict import sdict, set_item, get_item, unref

Log = getLogger(__name__)
_Type_BeforeSep = Literal["", "\n", ",", "k", ":", "v"]
"""k : v , \n"""
before_seps = args_of_type(_Type_BeforeSep)
_Type_DataOrComment = Literal["data", "comment"]


def _esc_for_regex(unEsc: str) -> str:
    return re.escape(unEsc).replace('"', '\\"')


def json_dumps(obj: Any, indent: int | None = 2) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=indent, cls=CompactJSONEncoder)


class Between[A, B](tuple[A, B]):
    """comment between 2 data-keys"""

    def __new__(cls, a: A, b: B) -> Self:
        return super().__new__(cls, (a, b))


def is_comment[A, B](key: Between[A, B] | Any) -> TypeIs[Between[A, B]]:
    return isinstance(key, Between)


class jsoncDict[K = str, V = Any](sdict[K, V]):
    """
    ### Usage
    life cycle: jsonc() init → user's `jc.insert_comment()` → `jc.full` from jc.dumps()
    ```python
    jc = jsoncDict(my_str, loads=hjson.loads)
    jc["//unique-keyname"] = "my comment but at end of body"
    jc.insert_comment({
        "/*\\nunique-keyname-1": "my multi-\\nline comments\\n",
        "//\\nunique-keyname-2": "my line-above comments",
        "\\//escape": ["treat as data, not comment, keyname is `//escape`"],
        "\\\\//escape": ["keyname is `\\//escape`"],
        }, "existedKey"
    )
    f.write(jc.full)
    ```
    """

    __dumps_raw = json_dumps
    slash_dash = True
    """default True. if key_name starts_with `/-`, like `/-mynode` will comment the whole tree node, see [kdl](https://kdl.dev/) config style"""
    auto_indent = True
    """default True, auto-indent for multi-line comment. if False, then you need manually handle indent"""
    header = ""
    footer = ""
    _parser = ts.Parser(ts.Language(ts_json.language()))
    """tree-sitter parser"""
    _COMMENT = f"_COMMENT-{uuid4().hex}"
    """for restore comments after dumps()"""

    def __init__(
        self,
        data: str | Mapping[K, V],
        loads: Callable[[str], Any] | None = None,
        dumps: Callable[[Any], str] = __dumps_raw,
        slash_dash: bool = slash_dash,
        auto_indent: bool = auto_indent,
        **kwargs: Unpack[sdict.Kwargs],
    ):
        """
        Args:
            data: raw text with comment
            loads: callable & able to parse `.jsonc` at least, to parse raw text, eg: `hjson.loads`
                **required** when raw `data` is str
            dumps: same as `loads`
            slash_dash: default True. If key_name starts_with `/-`, like `/-mynode` will comment the whole tree node, see [kdl](https://kdl.dev/) config style
            auto_indent: default True. Auto-indent for multi-line comment. if False, then you need manually handle indent
            **kwargs: see `sdict()`
        """
        self.__loads_raw = loads
        self.__dumps_raw = dumps
        self.slash_dash = slash_dash
        self.auto_indent = auto_indent

        if isinstance(data, str):
            if self.__loads_raw is None:
                raise ValueError("missing arg `loads` when `raw` is str")
            obj = self.__loads_raw(data)
        else:
            obj = data
            data = ""

        # NOTE: 其实raw(str)并不重要，我们只关心 data(dict)
        # `sdict.__init__` may call `self.__setitem__`, so setup attrs before this call.
        super().__init__(obj, **kwargs)
        self.comments: sdict[tuple[Any, Any], str] = sdict()
        """comments only, no data. eg: `{(dataKeyA, dataKeyB): "  // comment\n ..."}`"""
        self.loads(data)

    def _add_indent(self, comment: str, indent: str) -> str:
        """add indent before comment, used in restore phase"""
        if not self.auto_indent or "\n" not in comment:
            return comment
        return comment.replace("\n", "\n" + indent)

    def loads(self, raw: str) -> Mapping:
        """bake `self` data-only-dict with hint from `raw` (like `self`'s crutch🦯)"""
        if not raw:
            return {}
        raw = raw.replace("\r", "")

        byte = raw.encode()
        tree: ts.Tree = self._parser.parse(byte)
        head = True
        start = end = 0
        keyA = UNSET

        def dfs(node: ts.Node):
            nonlocal head, start, end, keyA
            if node.is_error:
                Log.error("tree-sitter-json: %s", node)
                return
            if head and node.type in ("object", "array"):
                head = False
                self.header = byte[: node.start_byte].decode()
                self.footer = byte[node.end_byte :].decode()
                # Log.debug("header: %s\nfooter:%s", self.header, self.footer)
            if not (node.is_named and node.text):
                return
            text = node.text.decode()

            if node.type == "comment":
                Log.debug("comment:\t%s", text)
                if start is None:
                    start = node.start_byte
                end = node.end_byte
                return
            elif node.type == "pair":
                # TODO: pair or array
                kNode = node.child_by_field_name("key")
                if kNode and kNode.type == "string":
                    content = kNode.child(1)
                    if content and content.text:
                        text = content.text.decode()

                ab = [(keyA, text)]
                self.comments[ab] = byte[start:end].decode()
                keyA = text
                start = None

                vNode = node.child_by_field_name("value")
                if vNode and vNode.type in ("object", "array"):
                    for child in node.children:
                        dfs(child)
            Log.debug("%s:\t%s\ntext:%s", node.type, node, text)
            for child in node.children:
                dfs(child)

        for child in tree.root_node.children:
            dfs(child)

        # NOTE: find footer

        return self

    def dumps(self, obj: Any | None = None, depth=0) -> str:
        """restore"""
        if obj is None:
            obj = self.v
        obj = unref(obj)
        inner = self.__dumps_raw(obj)
        # TODO: implement this

        return out

    def __call__(self, *key, **kw) -> Self:
        """
        `__call__` may undergo **breaking changes** in the future, based on its most common calling patterns and usage scenarios.
        """
        return self.mixed

    @property
    def mixed(self) -> Self:
        """mixed view of data & comment"""
        # TODO: implement this
        view = type(self)(self)
        return view

    @property
    def body(self) -> str:
        return self.dumps()

    @property
    def full(self) -> str:
        """header + body + footer"""
        return self.header + self.body + self.footer

    def getitem(
        self,
        key: Iterable,
        default=None,
        noRaise: tuple[type[BaseException], ...] = (
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
        ),
    ):
        return get_item(self.v, key, default, noRaise)

    def setitem(self, key: Sequence, value, at=UNSET):
        # TODO: self.v ? new logic in set_item()
        set_item(self if at is UNSET else at, key, value)


class hjsonDict[K = str, V = Any](jsoncDict[K, V]):
    _CommentPrefix = Literal["/*", "//", "#", "/-"]
    _comment_single: tuple[_CommentPrefix, ...] = ("//", "#")

    def _first_significant_char(self, text: str) -> tuple[str | None, int]:
        n = len(text)
        i = 0
        in_str = False
        escaped = False
        in_block = False
        in_line = False

        while i < n:
            c = text[i]
            if in_str:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    in_str = False
                i += 1
                continue
            if in_block:
                if text.startswith("*/", i):
                    in_block = False
                    i += 2
                    continue
                i += 1
                continue
            if in_line:
                if c == "\n":
                    in_line = False
                i += 1
                continue
            if c.isspace():
                i += 1
                continue
            if text.startswith("/*", i):
                in_block = True
                i += 2
                continue
            single_prefix = self._match_comment_single_prefix(text, i)
            if single_prefix is not None:
                in_line = True
                i += len(single_prefix)
                continue
            return c, i
        return None, -1

    def dumps(self, obj: Mapping | Sequence | None = None, depth=0) -> str:
        rendered = super().dumps(obj=obj, depth=depth)
        if depth != 0:
            return rendered
        target = unref(self.v if obj is None else obj)
        if not (
            getattr(self, "_rootless_object", False) and isinstance(target, Mapping)
        ):
            return rendered

        lines = rendered.splitlines()
        if len(lines) >= 2 and lines[0] == "{" and lines[-1] == "}":
            inner = lines[1:-1]
            return "\n".join(
                line[2:] if line.startswith("  ") else line for line in inner
            )
        return rendered


class CompactJSONEncoder(json.JSONEncoder):
    """A JSON Encoder that puts small containers on single lines. by @jannismain at: https://gist.github.com/jannismain/e96666ca4f059c3e5bc28abb711b5c92"""

    CONTAINER_TYPES = (list, tuple, dict)
    """Container datatypes include primitives or other containers."""

    MAX_WIDTH = 150
    """Maximum width of a container that might be put on a single line."""

    MAX_ITEMS = 10
    """Maximum number of items in container that might be put on single line."""

    def __init__(self, *args, **kwargs):
        # using this class without indentation is pointless
        if kwargs.get("indent") is None:
            kwargs["indent"] = 4
        super().__init__(*args, **kwargs)
        self.indentation_level = 0

    def encode(self, o):
        """Encode JSON object *o* with respect to single line lists."""
        if isinstance(o, (list, tuple)):
            return self._encode_list(o)
        if isinstance(o, dict):
            return self._encode_object(o)
        return json.dumps(
            o,
            skipkeys=self.skipkeys,
            ensure_ascii=self.ensure_ascii,
            check_circular=self.check_circular,
            allow_nan=self.allow_nan,
            sort_keys=self.sort_keys,
            indent=self.indent,
            separators=(self.item_separator, self.key_separator),
            default=self.default if hasattr(self, "default") else None,
        )

    def _encode_list(self, o):
        if self._put_on_single_line(o):
            return "[" + ", ".join(self.encode(el) for el in o) + "]"
        self.indentation_level += 1
        output = [self.indent_str + self.encode(el) for el in o]
        self.indentation_level -= 1
        return "[\n" + ",\n".join(output) + "\n" + self.indent_str + "]"

    def _encode_object(self, o):
        if not o:
            return "{}"

        # ensure keys are converted to strings
        o = {str(k) if k is not None else "null": v for k, v in o.items()}

        if self.sort_keys:
            o = dict(sorted(o.items(), key=lambda x: x[0]))

        if self._put_on_single_line(o):
            return (
                "{ "
                + ", ".join(
                    f"{self.encode(k)}: {self.encode(el)}" for k, el in o.items()
                )
                + " }"
            )

        self.indentation_level += 1
        output = [
            f"{self.indent_str}{self.encode(k)}: {self.encode(v)}" for k, v in o.items()
        ]
        self.indentation_level -= 1

        return "{\n" + ",\n".join(output) + "\n" + self.indent_str + "}"

    def iterencode(self, o, _one_shot: bool = False):
        """Required to also work with `json.dump`."""
        return self.encode(o)

    def _put_on_single_line(self, o):
        return (
            self._primitives_only(o)
            and len(o) <= self.MAX_ITEMS
            and len(str(o)) - 2 <= self.MAX_WIDTH
        )

    def _primitives_only(self, o: list | tuple | dict):
        if isinstance(o, (list, tuple)):
            return not any(isinstance(el, self.CONTAINER_TYPES) for el in o)
        elif isinstance(o, dict):
            return not any(isinstance(el, self.CONTAINER_TYPES) for el in o.values())

    @property
    def indent_str(self) -> str:
        if isinstance(self.indent, int):
            return " " * (self.indentation_level * self.indent)
        elif isinstance(self.indent, str):
            return self.indentation_level * self.indent
        else:
            raise ValueError(
                f"indent must either be of type int or str (is: {type(self.indent)})"
            )


# jsoncDict(
#     """
# {
#     // single-comment
#     "a": 1
#     /* multi-comment */
# }
# """.strip()
# )

# tree: ts.Tree = jsoncDict._parser.parse(
#     b"""
# {
#     // single-comment
#     "a": 1
#     /* multi-comment */
# }
# """.strip()
# )


# def print_tree(node: ts.Node, indent=0):
#     # 只打印具名节点 (过滤掉括号、等号等标点符号，如果想看全部可以去掉这个 if)
#     if node.is_named:
#         # 注意：text 返回的是 bytes，需要 decode 成字符串
#         if node.text:
#             text = node.text.decode("utf-8")
#             print(". " * indent + f"{node.type}: '{text}'")

#     # 递归遍历所有子节点
#     for child in node.children:
#         print_tree(child, indent + 1)


# print_tree(tree.root_node)
