#!/bin/env python3
"""
```
```
"""

import re
import json
from collections import OrderedDict
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
    Iterable,
    MutableMapping,
    Sized,
)
from typing import Any, Never, TypeIs, Unpack, Literal, cast, Self, overload

import tree_sitter as ts
import tree_sitter_json as ts_json

from jsonc_sdict.share import (
    SEED,
    NONE,
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


class Within[A, B = Never](tuple[A, B]):
    """Comment address in the mixed view.

    Shapes:
        `Within(left, right)`: comment between two neighboring logical data items.
        `Within(key)`: comment inside one object pair's `k:` / `:v` / `v,` slots.

    Boundary comments use `NONE` on one side, for example:
        `Within(NONE, first_key)`: before the first item.
        `Within(last_key, NONE)`: after the last item.
    """

    PREFIX = f"_Within_{SEED.hex}"
    """for restore comments after dumps()"""

    @overload
    def __new__(cls, a: A, b: B) -> Self:
        """comment between 2 data-keys"""

    @overload
    def __new__(cls, a: A) -> Self:
        """comments sandwiched in 1 data-key kv slot(`k:`/`:v`/`v,`)"""

    def __new__(cls, a: A, b: B | UNSET = UNSET) -> Self:
        if b is UNSET:
            ab = (a,)
        else:
            ab = cast(tuple[A, B], (a, b))
        return super().__new__(cls, ab)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}{tuple(self)}"

    def __str__(self) -> str:
        return f'{{"{self.PREFIX}":{json.dumps(list(self))}}}'


def is_comment[A, B](key: Within[A, B] | Any) -> TypeIs[Within[A, B]]:
    return isinstance(key, Within)


class jsoncDict[K = str, V = Any](MutableMapping[K, V]):
    """
    Mapping view over pure data plus comment layout metadata.

    `self.data` stores only real values. `self.comments` stores comment positions using
    `Within(...)` keys, so callers can read or edit comments without mixing them into the
    underlying data container.

    Usage:
    `jsonc()` init -> edit `jc.comments[...]` -> render with `jc.full`
    ```python
    jc = jsoncDict(my_str, loads=hjson.loads)
    jc.comments[Within("a", "b")] = "// between a and b"
    jc.comments[Within("b")] = {"k:": "/* before colon */"}
    jc.comments[Within("b", NONE)] = "// after b"
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
    _Type_kvSlot = (
        Within[Literal["k"], Literal[":"]]
        | Within[Literal[":"], Literal["v"]]
        | Within[Literal["v"], Literal[","]]
    )
    type _Type_comments = dict[
        K | Within[Any] | Within[Any, Any], str | dict[_Type_kvSlot, str]
    ]

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
            data: raw text with comment, or mixed view(Within as comment key)
            loads: callable & able to parse `.jsonc` at least, to parse raw text, eg: `hjson.loads`
                **required** when raw `data` is str
            dumps: same as `loads`
            slash_dash: default True. If key_name starts_with `/-`, like `/-mynode` will comment the whole tree node, see [kdl](https://kdl.dev/) config style
            auto_indent: default True. Auto-indent for multi-line comment. if False, then you need manually handle indent
            **kwargs: see `sdict()`
        """
        cls = type(self)
        cls.config(
            loads=loads, dumps=dumps, slash_dash=slash_dash, auto_indent=auto_indent
        )

        is_raw_str = isinstance(data, str)
        comments = {}
        if is_raw_str:
            if cls.__loads is None:
                raise ValueError("missing arg `loads` when `raw` is str")
            obj = cls.__loads(data)
        else:
            obj = data
            if isinstance(data, Mapping):
                obj, comments = self.split_mixed(data)

        # NOTE: 其实raw(str)并不重要，我们只关心 data(dict)
        # `sdict.__init__` may call `self.__setitem__`, so setup attrs before this call.
        self.data: sdict[K, V] = sdict(obj, **kwargs)
        """Pure data, no comment. Include `/-`(slash-dash) as data-key."""
        self.comments: jsoncDict._Type_comments = comments
        """Comment metadata and runtime-hidden keys for the current depth.

        Key shapes:
            `Within(left, right)`: comment between neighboring items.
            `Within(key)`: comments inside one pair's `k:` / `:v` / `v,` slots.
            `data_key`: runtime-hidden key; skip this data item in `items()`.

        Boundary comments use `NONE`:
        ```
        {
            Within(NONE, dataKeyA): "// before first item",
            Within(dataKeyA, dataKeyB): "  // between comment\\n ...",
            dataKeyB: "",  # runtime hidden
            Within(dataKeyC): {
                Within("k",":"): " /* 神人: */ // aaaa",
                Within(":","v"): " /* 神人v */ ",
                Within("v",","): " /* 神人, */ "
            },
            Within(dataKeyD, NONE): "// after last item"
        }
        ```
        """
        self.children: dict[K, Self] = {}
        """child proxy cache, also carries nested comments for child jsoncDict views"""
        if not is_raw_str and isinstance(data, Mapping):
            self.children = self.__children_build(data)
        if is_raw_str:
            self.loads(data)

    def Proxy(
        self,
        data: sdict[K, V],
        comments: _Type_comments | None = None,
        children: dict[Any, Self] | None = None,
    ) -> Self:
        """return new jsoncDict for self mixed-view children"""
        node = cast(Self, type(self).__new__(type(self)))
        node.data = data
        node.comments = comments if comments else {}
        node.children = children if children else {}
        return node

    # mixed view helpers
    def split_mixed(self, mapping: Mapping) -> tuple[OrderedDict, _Type_comments]:
        """Split a mixed mapping into pure data and comment metadata.

        The input may contain normal data keys, `Within(...)` comment keys, or nested mixed
        mappings. The returned `OrderedDict` keeps only real data, while the comment dict keeps
        the comment addresses needed to reconstruct the mixed view.
        """
        data_out: OrderedDict = OrderedDict()
        comments_out: jsoncDict._Type_comments = {}

        for key, value in mapping.items():
            if is_comment(key):
                comments_out[key] = value
                continue
            if not isinstance(value, Mapping):
                data_out[key] = value
                continue

            child_data, child_comments, comment_only = self.__mixed_split_child_mapping(
                value
            )
            if comment_only:
                comments_out[key] = child_comments
                continue

            data_out[key] = child_data

        return data_out, comments_out

    def __mixed_split_child_mapping(
        self, value: Mapping[Any, Any]
    ) -> tuple[OrderedDict, _Type_comments, bool]:
        """Split a nested mixed mapping into child data/comments and detect comment-only nodes."""
        child_data, child_comments = self.split_mixed(value)
        comment_only = (
            bool(child_comments)
            and not child_data
            and all(is_comment(child_key) for child_key in value)
        )
        return child_data, child_comments, comment_only

    # child proxy helpers
    def __children_build(self, mapping: Mapping[Any, Any]) -> dict[Any, Self]:
        """Build cached child proxies for nested mapping values present in pure data."""
        children: dict[Any, Self] = {}
        for key, value in mapping.items():
            if (
                is_comment(key)
                or not isinstance(value, Mapping)
                or key not in self.data
            ):
                continue
            data_value = self.data[key]
            if not isinstance(data_value, sdict):
                continue
            _, child_comments, comment_only = self.__mixed_split_child_mapping(value)
            if comment_only:
                continue
            child = self.Proxy(data_value, comments=child_comments)
            child.children = child.__children_build(value)
            children[key] = child
        return children

    def __children_iter(self) -> Iterable[tuple[Any, Self]]:
        """Yield `(key, child)` pairs for nested `sdict` values as `jsoncDict` proxies."""
        for key, _ in self.__data_items():
            child = self.__children_get(key)
            if isinstance(child, jsoncDict):
                yield key, child

    def __children_sync(self) -> None:
        """Drop stale child proxies and rebind preserved ones after `self.data` mutations."""
        current: dict[Any, Self] = {}
        by_data_id = {id(child.data): child for child in self.children.values()}
        for key, value in self.__data_items():
            if not isinstance(value, sdict):
                continue
            child = self.children.get(key)
            if child is None or child.data is not value:
                child = by_data_id.get(id(value))
            if child is not None and child.data is value:
                current[key] = child
        self.children = current

    @staticmethod
    def _is_keypath(key: Any) -> TypeIs[Sequence]:
        return isinstance(key, Sequence) and not isinstance(
            key, (str, bytes, bytearray, Within)
        )

    def __children_get(self, key: Any):
        """Return the mixed-view child proxy for `key`, creating it lazily when needed."""
        self.__children_sync()
        value = self.data[key]
        if not isinstance(value, sdict):
            return value
        child = self.children.get(key)
        if child is not None and child.data is value:
            return child

        child = self.Proxy(value)
        self.children[key] = child
        return child

    def __data_items(self) -> Iterable[tuple[Any, Any]]:
        """Iterate pure data items in storage order, excluding synthetic comment entries."""
        return self.data.getChild(self.data, self.data.v)

    # maintenance helpers
    def rebuild(self):
        self.data.rebuild()
        self.children.clear()
        return self

    # loads helpers
    def __loads_root_container(self, root: ts.Node) -> ts.Node | None:
        """Return the top-level object/array node parsed from the source text."""
        for child in root.children:
            if child.type in ("object", "array"):
                return child
        return None

    def __loads_pair_key(self, node: ts.Node) -> Any:
        """Decode an object pair node into its logical key."""
        key = node.child_by_field_name("key")
        if key and key.type == "string":
            content = key.child(1)
            if content and content.text:
                return content.text.decode()
        raise ValueError(f"unsupported json object key node: {node}")

    def __loads_is_item(self, container: ts.Node, node: ts.Node) -> bool:
        """Check whether a child node represents a real container item, not a comment."""
        if not node.is_named or node.type == "comment":
            return False
        return node.type == "pair" if container.type == "object" else True

    def __loads_set_comment(
        self, owner: Self, key_a: Any, key_b: Any, text: str
    ) -> None:
        """Store a non-empty comment span between two logical item positions."""
        if text:
            owner.comments[Within(key_a, key_b)] = text

    def __loads_reset_comments(self, owner: Self) -> None:
        """Clear parsed comment metadata recursively before a fresh `loads()` pass."""
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
            child = owner.__children_get(key)
            if isinstance(child, jsoncDict):
                self.__loads_reset_comments(child)

    def __loads_collect_inner_comment(
        self, owner: Self, node: ts.Node, byte: bytes
    ) -> None:
        """Capture comments lexically inside one object pair as single-key slot annotations."""
        if node.type != "pair":
            return
        comments = [child for child in node.children if child.type == "comment"]
        if not comments:
            return
        key = self.__loads_pair_key(node)
        owner.comments[Within(key)] = byte[
            comments[0].start_byte : comments[-1].end_byte
        ].decode()

    def __loads_walk_container(
        self, owner: Self, container: ts.Node, byte: bytes
    ) -> None:
        """Walk one parsed object/array and assign surrounding comments to logical slots."""
        prev_key = NONE
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

            # Object items use parsed keys; array items use the running index.
            key = self.__loads_pair_key(child) if container.type == "object" else index
            if pending_start is not None and pending_end is not None:
                self.__loads_set_comment(
                    owner, prev_key, key, byte[pending_start:pending_end].decode()
                )
                pending_start = pending_end = None

            self.__loads_collect_inner_comment(owner, child, byte)
            # Pair nodes store the nested container under the `value` field.
            value = child.child_by_field_name("value") or child
            if value.type in ("object", "array"):
                child_owner = owner[key]
                if isinstance(child_owner, jsoncDict):
                    self.__loads_walk_container(child_owner, value, byte)

            prev_key = key
            if container.type == "array":
                index += 1

        if pending_start is not None and pending_end is not None:
            self.__loads_set_comment(
                owner, prev_key, NONE, byte[pending_start:pending_end].decode()
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

    # dumps helpers
    def dumps(self, obj: Any | None = None) -> str:
        """dumps self.mixed by __dumps"""
        # 1. 将Within转为json能接受的str (如何设计???), 带前缀以区别data/comment key( _COMMENT = f"_COMMENT_{uuid4().hex}:" ), 如"_COMMENT_...:[\"dataKeyA\",\"dataKeyB\"]"
        # 2. __dumps()
        # 3. 分歧点
        # 3.1 直接定位comment-key: 通过 .startswith(Within._COMMENT) 来定位comment-key，然后使用 __DUMPS_STOP = regex.compile('[^\\]"') 类似的来寻找key的结尾。
        # 3.2 先定位data-key，然后上下文搜索找到 comment-key:
        #   通过 _esc_for_regex(key) for key in self.mixed.keys() 来获得data-key的位置，然后向上&向下搜索 Within._COMMENT 与 comment-key的 end_pos.
        #   由于data-key在同一层dict里是唯一的，所以可以直接让comment-key变得更短?
        # 这样得到了key的start_pos与end_pos。然后就可以将对应的 : "value..." 里面存储的原始的
        if obj is None:
            obj = self.mixed
        # TODO: implement this
        return

    def _dumps_add_indent(self, comment: str, indent: str) -> str:
        """add indent before comment, used in restore phase"""
        if not type(self).auto_indent or "\n" not in comment:
            return comment
        return comment.replace("\n", "\n" + indent)

    @property
    def mixed(self) -> OrderedDict[Any, Any]:
        """Materialize the current mixed view as an `OrderedDict`."""
        return OrderedDict(self.items())

    @property
    def comments_flat(self) -> dict[tuple, jsoncDict._Type_comments]:
        """Flatten nested `comments` dicts by `self.data.keypath`.

        Example:
            `{(): root_comments, ("a",): child_comments, ("a", "b"): grandchild_comments}`
        """
        out: dict[tuple, jsoncDict._Type_comments] = {}

        def collect(node: Self) -> None:
            if node.comments:
                out[node.data.keypath] = dict(node.comments)
            for _, child in node.__children_iter():
                collect(child)

        collect(self)
        return out

    def items(self) -> Iterable[tuple[K | Within, V | str | dict]]:  # type: ignore
        """Iterate the exported mixed view in display order.

        Yields:
            `Within(left, right), str` for between-item comments.
            `key, value` for visible data items.
            `Within(key), dict[_Type_kvSlot, str] | str` for single-item slot comments.
            `Within(last_key, NONE), str` for trailing comments.
        """
        prev_key = NONE

        for key, _ in self.__data_items():
            comment = self.comments.get(Within(prev_key, key))
            if comment is not None:
                yield Within(prev_key, key), comment
            if key in self.comments and not is_comment(key):
                prev_key = key
                continue
            yield key, self.__children_get(key)
            comment = self.comments.get(Within(key))
            if comment is not None:
                yield Within(key), comment
            prev_key = key

        comment = self.comments.get(Within(prev_key, NONE))
        if comment is not None:
            yield Within(prev_key, NONE), comment

    def keys(self) -> Iterable[K | Within]:  # type: ignore
        for key, _ in self.items():
            yield key

    def __getitem__(self, key):
        if self._is_keypath(key):
            value = self
            for part in key:
                value = value[part]
            return value
        if key in self.comments and not is_comment(key):
            raise KeyError(key)
        # Mixed lookup walks comments and data in the same exported iteration order.
        for item_key, value in self.items():
            if item_key == key:
                return value
        raise KeyError(key)

    def __setitem__(self, key, value) -> None:
        if is_comment(key):
            self.comments[key] = value
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
            del self.comments[key]
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
        return iter(self.keys())

    def __len__(self) -> int:
        return sum(1 for _ in self.items())

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
