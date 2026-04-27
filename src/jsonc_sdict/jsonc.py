#!/bin/env python3
"""
```
```
"""

import re
import json
from uuid import uuid4
from collections import OrderedDict
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
    Iterable,
    MutableMapping,
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
from jsonc_sdict.Sdict import sdict, unref

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

    _COMMENT = f"_COMMENT-{uuid4().hex}"
    """for restore comments after dumps()"""

    def __new__(cls, a: A, b: B) -> Self:
        return super().__new__(cls, (a, b))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}{self[0], self[1]}"


def is_comment[A, B](key: Between[A, B] | Any) -> TypeIs[Between[A, B]]:
    return isinstance(key, Between)


class jsoncDict[K = str, V = Any](MutableMapping[K, V]):
    """
    ### Usage
    life cycle: jsonc() init → user's `jc.comments[(dataKeyA, dataKeyB)] = "..."` → `jc.full` from jc.dumps()
    ```python
    jc = jsoncDict(my_str, loads=hjson.loads)
    # TODO: update doc
    ```
    """

    __loads: Callable[[str], Any]
    """callable & able to parse `.jsonc` at least, to parse raw text, eg: `hjson.loads`"""
    __dumps: Callable[[Any], str] = json_dumps
    """same as `__loads`"""
    slash_dash = True
    """default True. if key_name starts_with `/-`, like `/-mynode` will comment the whole tree node, see [kdl](https://kdl.dev/) config style"""
    auto_indent = True
    """default True, auto-indent for multi-line comment. if False, then you need manually handle indent"""
    header = ""
    footer = ""
    _parser = ts.Parser(ts.Language(ts_json.language()))
    """tree-sitter parser"""

    @classmethod
    def config(
        cls,
        *,
        loads: Callable[[str], Any] | UNSET = UNSET,
        dumps: Callable[[Any], str] | UNSET = UNSET,
        slash_dash: bool | UNSET = UNSET,
        auto_indent: bool | UNSET = UNSET,
    ) -> None:
        if loads is not UNSET:
            cls.__loads = loads
        if dumps is not UNSET:
            cls.__dumps = dumps
        if slash_dash is not UNSET:
            cls.slash_dash = slash_dash
        if auto_indent is not UNSET:
            cls.auto_indent = auto_indent

    def __init__(
        self,
        data: str | Mapping[K, V],
        loads: Callable[[str], Any] | UNSET = UNSET,
        dumps: Callable[[Any], str] | UNSET = UNSET,
        slash_dash: bool | UNSET = UNSET,
        auto_indent: bool | UNSET = UNSET,
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
        cls = type(self)
        cls.config(
            loads=loads,
            dumps=dumps,
            slash_dash=slash_dash,
            auto_indent=auto_indent,
        )

        if isinstance(data, str):
            loads_fn = cls.__loads
            if loads_fn is None:
                raise ValueError("missing arg `loads` when `raw` is str")
            obj = loads_fn(data)
        else:
            obj = data
            data = ""

        # NOTE: 其实raw(str)并不重要，我们只关心 data(dict)
        # `sdict.__init__` may call `self.__setitem__`, so setup attrs before this call.
        self.data: sdict[K, V] = sdict(obj, **kwargs)
        """Pure data, no comment. Include `/-`(slash-dash) as data-key."""
        self.comments: dict[tuple[Any, Any], str] = {}
        """Only comments on current depth, no data. eg: `{(dataKeyA, dataKeyB): "  // comment\n ..."}`"""
        self.commentKeys = []
        """for switch() to record status for commented or not, **on current depth**"""
        self.children: dict[K, Self] = {}
        """cache to maintain jsoncDict proxy childrens"""
        self.loads(data)

    def Proxy(self, data: sdict[K, V]) -> Self:
        """return new jsoncDict for self.mixed's children"""
        node = cast(Self, type(self).__new__(type(self)))
        node.data = data
        node.comments = {}
        node.commentKeys = []
        node.children = {}
        return node

    def _add_indent(self, comment: str, indent: str) -> str:
        """add indent before comment, used in restore phase"""
        if not type(self).auto_indent or "\n" not in comment:
            return comment
        return comment.replace("\n", "\n" + indent)

    @staticmethod
    def _is_keypath(key: Any) -> TypeIs[Sequence]:
        return isinstance(key, Sequence) and not isinstance(
            key, (str, bytes, bytearray, Between)
        )

    def _child(self, key: Any):
        self._sync_children()
        value = self.data[key]
        if not isinstance(value, sdict):
            return value
        child = self.children.get(key)
        if child is not None and child.data is value:
            return child

        child = self.Proxy(value)
        self.children[key] = child
        return child

    def _iter_data_items(self) -> Iterable[tuple[Any, Any]]:
        return self.data.getChild(self.data, self.data.v)

    def _sync_children(self) -> None:
        current: dict[Any, Self] = {}
        by_data_id = {id(child.data): child for child in self.children.values()}
        for key, value in self._iter_data_items():
            if isinstance(value, sdict):
                child = by_data_id.get(id(value))
                if child is not None:
                    current[key] = child
        self.children = current

    def rebuild(self):
        self.data.rebuild()
        self.children.clear()
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
            owner.comments[(key_a, key_b)] = text

    def __loads_reset_comments(self, owner: Self) -> None:
        if owner is self:
            owner.header = ""
            owner.footer = ""
        owner.comments = {}
        owner.children.clear()
        raw = owner.data.v
        if isinstance(raw, Mapping):
            keys = raw.keys()
        elif iterable(raw):
            keys = range(len(raw))
        else:
            return
        for key in keys:
            child = owner._child(key)
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

    def dumps(self, obj: Any | None = None) -> str:
        """需要先将Between转为"""
        if obj is None:
            obj = self.data.v
        obj = unref(obj)
        mixed = type(self).__dumps(obj)
        # TODO: implement this

        return out

    @property
    def mixed(self) -> OrderedDict[Any, Any]:
        out: OrderedDict[Any, Any] = OrderedDict()
        prev_key = UNSET

        for key, _ in self._iter_data_items():
            comment = self.comments.get((prev_key, key))
            if comment is not None:
                out[Between(prev_key, key)] = comment
            out[key] = self._child(key)
            comment = self.comments.get((key, key))
            if comment is not None:
                out[Between(key, key)] = comment
            prev_key = key

        comment = self.comments.get((prev_key, UNSET))
        if comment is not None:
            out[Between(prev_key, UNSET)] = comment
        return out

    @property
    def comments_flat(self) -> dict[tuple, dict[tuple[Any, Any], str]]:
        """computed from children's comments. eg: `{(): {...}, ("keypath"): {...}, ("kp1","kp2"): {...}}`"""
        out: dict[tuple, dict[tuple[Any, Any], str]] = {}

        def collect(node: Self) -> None:
            if node.comments:
                out[node.data.keypath] = dict(node.comments)
            for key, _ in node._iter_data_items():
                child = node._child(key)
                if isinstance(child, jsoncDict):
                    collect(child)

        collect(self)
        return out

    @property
    def commentKeys_flat(self) -> dict[tuple, list[str]]:
        """computed from children's commentKeys. eg: `{():[...], ("keypath"):[...], ("kp1","kp2"):[...]}`"""
        out: dict[tuple, list[str]] = {}

        def collect(node: Self) -> None:
            if node.commentKeys:
                out[node.data.keypath] = node.commentKeys
            for key, _ in node._iter_data_items():
                child = node._child(key)
                if isinstance(child, jsoncDict):
                    collect(child)

        collect(self)
        return out

    def __getitem__(self, key):
        if self._is_keypath(key):
            value = self
            for part in key:
                value = value[part]
            return value
        return self.mixed[key]

    def __setitem__(self, key, value) -> None:
        if is_comment(key):
            self.comments[tuple(key)] = value
            return
        if self._is_keypath(key):
            keys = tuple(key)
            if not keys:
                raise KeyError(key)
            parent = self if len(keys) == 1 else self[keys[:-1]]
            parent[keys[-1]] = value
            return
        self.data[key] = value
        self.children.pop(key, None)

    def __delitem__(self, key) -> None:
        if is_comment(key):
            del self.comments[tuple(key)]
            return
        if self._is_keypath(key):
            keys = tuple(key)
            if not keys:
                raise KeyError(key)
            if len(keys) == 1:
                del self[keys[0]]
                return
            parent = self[keys[:-1]]
            del parent[keys[-1]]
            return
        del self.data[key]
        self.children.pop(key, None)

    def __iter__(self):
        return iter(self.mixed)

    def __len__(self) -> int:
        return len(self.mixed)

    @property
    def body(self) -> str:
        return self.dumps()

    @property
    def full(self) -> str:
        """header + body + footer"""
        return self.header + self.body + self.footer


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
