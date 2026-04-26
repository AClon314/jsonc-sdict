#!/bin/env python3
"""
```
```
"""

import re
import json
from uuid import uuid4
from collections import OrderedDict
from weakref import WeakKeyDictionary
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
    Iterable,
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
from jsonc_sdict.Sdict import sdict, dfs, set_item, get_item, unref

Log = getLogger(__name__)
_Type_BeforeSep = Literal["", "\n", ",", "k", ":", "v"]
"""k : v , \n"""
before_seps = args_of_type(_Type_BeforeSep)


def _esc_for_regex(unEsc: str) -> str:
    return re.escape(unEsc).replace('"', '\\"')


def json_dumps(obj: Any, indent: int | None = 2) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=indent, cls=CompactJSONEncoder)


class Between[A, B](tuple[A, B]):
    """comment between 2 data-keys"""

    def __new__(cls, a: A, b: B) -> Self:
        return super().__new__(cls, (a, b))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}{self[0], self[1]}"


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

    __dumps = json_dumps
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
        dumps: Callable[[Any], str] = __dumps,
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
        self.__loads = loads
        self.__dumps = dumps
        self.slash_dash = slash_dash
        self.auto_indent = auto_indent

        if isinstance(data, str):
            if self.__loads is None:
                raise ValueError("missing arg `loads` when `raw` is str")
            obj = self.__loads(data)
        else:
            obj = data
            data = ""

        # NOTE: 其实raw(str)并不重要，我们只关心 data(dict)
        # `sdict.__init__` may call `self.__setitem__`, so setup attrs before this call.
        super().__init__(obj, **kwargs)
        self._comments: dict[tuple[Any, Any], str] = {}
        """comments on current depth only, no data. eg: `{(dataKeyA, dataKeyB): "  // comment\n ..."}`"""
        self.loads(data)

    def _add_indent(self, comment: str, indent: str) -> str:
        """add indent before comment, used in restore phase"""
        if not self.auto_indent or "\n" not in comment:
            return comment
        return comment.replace("\n", "\n" + indent)

    @staticmethod
    def _is_keypath(key: Any) -> TypeIs[Sequence]:
        return isinstance(key, Sequence) and not isinstance(
            key, (str, bytes, bytearray, Between)
        )

    def rebuild(self):
        self.forkGraph = WeakKeyDictionary()
        nodes = tuple(
            dfs(
                self,
                cls=type(self),
                forkGraph=self.forkGraph,
                pathCount=self.pathCount,
                getChild=self.getChild,
            )
        )
        for node in nodes:
            if not isinstance(node, jsoncDict):
                continue
            node.__loads = self.__loads
            node.__dumps = self.__dumps
            node.slash_dash = self.slash_dash
            node.auto_indent = self.auto_indent
            node._comments = getattr(node, "_comments", {})
        self.del_cache()
        return self

    def __loads_root_container(self, root: ts.Node) -> ts.Node | None:
        for child in root.children:
            if child.type in ("object", "array"):
                return child
        return None

    def __loads_pair_key(self, node: ts.Node) -> Any:
        key = node.child_by_field_name("key")
        if key and key.type == "string":
            content = key.child(1)
            if content and content.text:
                return content.text.decode()
        raise ValueError(f"unsupported json object key node: {node}")

    def __loads_item_key(self, container: ts.Node, node: ts.Node, index: int) -> Any:
        if container.type == "object":
            return self.__loads_pair_key(node)
        return index

    def __loads_item_value(self, node: ts.Node) -> ts.Node:
        return node.child_by_field_name("value") or node

    def __loads_is_item(self, container: ts.Node, node: ts.Node) -> bool:
        if not node.is_named or node.type == "comment":
            return False
        return node.type == "pair" if container.type == "object" else True

    def __loads_set_comment(
        self, owner: Self, key_a: Any, key_b: Any, text: str
    ) -> None:
        if text:
            owner._comments[(key_a, key_b)] = text

    def __loads_reset_comments(self, owner: Self) -> None:
        owner.header = ""
        owner.footer = ""
        owner._comments = {}
        raw = owner.v
        if isinstance(raw, Mapping):
            keys = raw.keys()
        elif iterable(raw):
            keys = range(len(raw))
        else:
            return
        for key in keys:
            child = owner[key]
            if isinstance(child, jsoncDict):
                self.__loads_reset_comments(child)

    def __loads_collect_inner_comment(
        self, owner: Self, node: ts.Node, byte: bytes
    ) -> None:
        if node.type != "pair":
            return
        comments = [child for child in node.children if child.type == "comment"]
        if not comments:
            return
        key = self.__loads_pair_key(node)
        self.__loads_set_comment(
            owner,
            key,
            key,
            byte[comments[0].start_byte : comments[-1].end_byte].decode(),
        )

    def __loads_walk_container(
        self, owner: Self, container: ts.Node, byte: bytes
    ) -> None:
        prev_key = UNSET
        pending_start: int | None = None
        pending_end: int | None = None
        index = 0

        for child in container.children:
            if child.type == "comment":
                if pending_start is None:
                    pending_start = child.start_byte
                pending_end = child.end_byte
                continue
            if not self.__loads_is_item(container, child):
                continue

            key = self.__loads_item_key(container, child, index)
            if pending_start is not None and pending_end is not None:
                self.__loads_set_comment(
                    owner, prev_key, key, byte[pending_start:pending_end].decode()
                )
                pending_start = pending_end = None

            self.__loads_collect_inner_comment(owner, child, byte)
            value = self.__loads_item_value(child)
            if value.type in ("object", "array"):
                child_owner = owner[key]
                if isinstance(child_owner, jsoncDict):
                    self.__loads_walk_container(child_owner, value, byte)

            prev_key = key
            if container.type == "array":
                index += 1

        if pending_start is not None and pending_end is not None:
            self.__loads_set_comment(
                owner, prev_key, UNSET, byte[pending_start:pending_end].decode()
            )

    def loads(self, raw: str) -> Self:
        """Bake comment layout hints from `raw` into `self.comments`, `header`, and `footer`."""
        self.__loads_reset_comments(self)
        if not raw:
            return self

        raw = raw.replace("\r", "")
        byte = raw.encode()
        tree: ts.Tree = self._parser.parse(byte)
        root = tree.root_node
        if root.is_error:
            Log.error("tree-sitter-json: %s", root)
            return self

        container = self.__loads_root_container(root)
        if container is None:
            self.header = raw
            return self

        self.header = byte[: container.start_byte].decode()
        self.footer = byte[container.end_byte :].decode()
        self.__loads_walk_container(self, container, byte)
        return self

    def dumps(self, obj: Any | None = None, depth=0) -> str:
        """restore"""
        if obj is None:
            obj = self.v
        obj = unref(obj)
        mixed = self.__dumps(obj)
        # TODO: implement this

        return out

    @property
    def comments(self) -> dict[tuple, dict[tuple[Any, Any], str]]:
        """computed from children's _comments. eg: `{(): {...}, ("keypath_child"): {...}, ("kp1","kp2"): {...}}`"""
        out: dict[tuple, dict[tuple[Any, Any], str]] = {}

        def collect(node: Self) -> None:
            if node._comments:
                out[node.keypath] = dict(node._comments)
            for _, child in node.getChild(node, node.v):
                if isinstance(child, jsoncDict):
                    collect(child)

        collect(self)
        return out

    def __call__(self, *key, **kw) -> Self:
        """
        return mixed
        `__call__` may undergo **breaking changes** in the future, based on its most common calling patterns and usage scenarios.
        """
        return self.mixed

    @property
    def mixed(self) -> Self:
        """mixed view of data & comment. Comment-key will be translated into Between(), which stays tuple in self.comments"""
        mix = type(self)(
            {},
            loads=self.__loads,
            dumps=self.__dumps,
            slash_dash=self.slash_dash,
            auto_indent=self.auto_indent,
            deep=False,
        )
        prev_key = UNSET

        def put(key, value) -> None:
            OrderedDict.__setitem__(mix, key, value)

        def put_comment(key_a, key_b) -> None:
            comment = self._comments.get((key_a, key_b))
            if comment is not None:
                put(Between(key_a, key_b), comment)

        for key, value in self.getChild(self, self.v):
            put_comment(prev_key, key)
            if isinstance(value, jsoncDict):
                value = value.mixed
            put(key, value)
            put_comment(key, key)
            prev_key = key

        put_comment(prev_key, UNSET)
        return mix

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
        set_item(self if at is UNSET else at, key, value)


class hjsonDict[K = str, V = Any](jsoncDict[K, V]):
    pass
    # TODO


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
