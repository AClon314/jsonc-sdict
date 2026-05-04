#!/bin/env python3
"""Round-trip JSONC/HJSON editing with dict-like APIs.

Quick usage:
```python
import hjson
from jsonc_sdict import jsoncDict, Within, NONE

jc = jsoncDict('{"a": 1}', loads=hjson.loads, dumps=hjson.dumps)
jc["a"] = 2
jc[Within(NONE, "a")] = "// before a"
print(jc.full)
```

Advanced usage:
```python
jc[Within("a")] = {
    Within("k", ":"): "/* key slot */",
    Within(":", "v"): "/* value slot */",
    Within("v", ","): "/* tail slot */",
}
print(jc.full)
```
"""

import json
from collections import OrderedDict
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
    Iterable,
    MutableMapping,
    Sized,
    Iterator,
)
from typing import Any, Never, TypeIs, Unpack, Literal, cast, Self, overload

import tree_sitter as ts
import tree_sitter_json as ts_json

from jsonc_sdict.share import (
    NONE,
    UNSET,
    getLogger,
    iterable,
    args_of_type,
    unpack_method,
    _TODO,
)
from jsonc_sdict.Sdict import sdict, unref
from jsonc_sdict.Merge import merge as _merge

Log = getLogger(__name__)
_Type_BeforeSep = Literal["", "\n", ",", "k", ":", "v"]
"""k : v , \n"""
before_seps = args_of_type(_Type_BeforeSep)


def json_dumps(obj: Any, indent: int | None = 2, **kw) -> str:
    kwargs = dict(ensure_ascii=False, indent=indent, cls=CompactJSONEncoder)
    kwargs.update(kw)
    return json.dumps(obj, **kwargs)  # type: ignore


class Within[A, B](tuple[A, B]):
    """Address a **comment** slot in the mixed view.

    Shapes:
        `Within(left, right)`: comment between two neighboring logical items.
        `Within(key)`: comment attached to one pair's internal `k:` / `:v` / `v,`
        slots.

    Boundary comments use `NONE` on one side:
        `Within(NONE, first_key)`: comment before the first item.
        `Within(last_key, NONE)`: comment after the last item.
    """

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
        return f"{type(self).__name__}{super().__repr__()}"

    def __eq__(self, obj) -> bool:
        return isinstance(obj, type(self)) and super().__eq__(obj)

    def __ne__(self, obj) -> bool:
        return not self.__eq__(obj)

    def __hash__(self) -> int:
        return super().__hash__()


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

    _loads: Callable[[str], Any]
    """callable & able to parse `.jsonc` at least, to parse raw text, eg: `hjson.loads`"""
    _dumps: Callable[[Any], str] = json_dumps
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
    type _Type_comments = dict[K | Within, str | dict[_Type_kvSlot, str]]

    @classmethod
    def config(
        cls,
        *,
        loads: Callable[[str], Any] | UNSET = UNSET,
        dumps: Callable[[Any], str] | UNSET = UNSET,
        slash_dash: bool | UNSET = UNSET,
        auto_indent: bool | UNSET = UNSET,
    ) -> type[Self]:
        if loads is not UNSET:
            cls._loads = loads
        if dumps is not UNSET:
            cls._dumps = dumps
        if slash_dash is not UNSET:
            cls.slash_dash = slash_dash
        if auto_indent is not UNSET:
            cls.auto_indent = auto_indent
        return cls

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
            if cls._loads is None:
                raise ValueError("missing arg `loads` when `raw` is str")
            obj = cls._loads(data)
        else:
            obj = data
            if isinstance(data, Mapping):
                obj, comments = self.split_mixed(data)

        # NOTE: 其实raw(str)并不重要，我们只关心 data(dict)
        # `sdict.__init__` may call `self.__setitem__`, so setup attrs before this call.
        self.data: sdict[K, V] = sdict(obj, **kwargs)
        """Pure raw data, no Within comment. Include `/-`(slash-dash) as data-key."""
        self.comments: jsoncDict._Type_comments = comments
        """Comment metadata and **runtime-hidden keys** for the current depth.

        Key shapes:
            `Within(left, right)`: comment between neighboring items.
            `Within(key)`: comments inside one pair's `k:` / `:v` / `v,` slots.
            `data_key`: runtime-hidden key; skip this data item in `items()`.

        Boundary comments use `NONE`:
        ```
        {
            Within(NONE, dataKeyA): "// before first item",
            Within(dataKeyA, dataKeyB): "  // between comment\\n ...",
            dataKeyB: "",  # runtime hidden; presence in `comments` means hidden
            Within(dataKeyC): {
                Within("k",":"): " /* key slot */",
                Within(":","v"): " /* value slot */ ",
                Within("v",","): " /* tail slot, */ "
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

    @staticmethod
    def is_keypath(key: Any) -> TypeIs[Sequence]:
        return isinstance(key, Sequence) and not isinstance(
            key, (str, bytes, bytearray, Within)
        )

    # mixed view helpers
    @classmethod
    def split_mixed(cls, mixed: Mapping) -> tuple[OrderedDict, _Type_comments]:
        """Split a mixed mapping into pure data and comment metadata.

        The input may contain normal data keys, `Within(...)` comment keys, or nested mixed
        mappings. The returned `OrderedDict` keeps only real data, while the comment dict keeps
        the comment addresses needed to reconstruct the mixed view.
        """
        data_out: OrderedDict = OrderedDict()
        comments_out: jsoncDict._Type_comments = {}

        for key, value in mixed.items():
            if is_comment(key):
                comments_out[key] = value
                continue
            if not isinstance(value, Mapping):
                data_out[key] = value
                continue

            child_data, child_comments, comment_only = cls._split_mixed_child_mapping(
                value
            )
            if comment_only:
                comments_out[key] = child_comments
                continue

            data_out[key] = child_data

        return data_out, comments_out

    @classmethod
    def _split_mixed_child_mapping(
        cls, value: Mapping[Any, Any]
    ) -> tuple[OrderedDict, _Type_comments, bool]:
        """Split a nested mixed mapping into child data/comments and detect comment-only nodes."""
        child_data, child_comments = cls.split_mixed(value)
        comment_only = (
            bool(child_comments)
            and not child_data
            and all(is_comment(child_key) for child_key in value)
        )
        return child_data, child_comments, comment_only

    def merge(self, mixed: Mapping, **kw: Unpack[_merge.Kwargs]):
        data_only = {k: v for k, v in mixed.items() if not is_comment(k)}
        comment_only = {k: v for k, v in mixed.items() if is_comment(k)}
        self.data.merge(data_only, **kw)
        # TODO: solve comment conflict?
        self.comments = _merge((self.comments, comment_only), **kw)()

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
            _, child_comments, comment_only = self._split_mixed_child_mapping(value)
            if comment_only:
                continue
            child = self.Proxy(data_value, comments=child_comments)
            child.children = child.__children_build(value)
            children[key] = child
        return children

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
        get_child = unpack_method(getattr(type(self.data), "getChild"), type(self.data))
        if get_child is None:
            get_child = self.data.getChild
        return get_child(self.data, self.data.v)

    # maintenance helpers
    def rebuild(self):
        """Rebuild `sdict` caches for `self.data` and drop stale child proxies."""
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

    def _slash_dash_key(self, key: Any) -> str | None:
        """Return the logical key behind one `/-name` marker key."""
        if type(self).slash_dash and isinstance(key, str) and key.startswith("/-"):
            return key[2:]
        return None

    def __key_from_serialized(self, owner: Self, key: Any) -> Any:
        """Map one serialized object key back to the logical key stored in `owner.data`."""
        logical = self._slash_dash_key(key)
        if logical is None:
            return key
        if logical in owner.data and logical in owner.comments:
            return logical
        return key

    def __loads_normalize_slash_dash(self, owner: Self) -> None:
        """Normalize slash-dash keys into logical keys when doing so is conflict-free."""
        raw = owner.data.v
        if isinstance(raw, Mapping):
            for key in list(raw.keys()):
                logical = self._slash_dash_key(key)
                if logical is None or logical in raw:
                    continue
                owner.data.rename_key(key, logical, deep=False)
                owner.comments[logical] = ""

        if isinstance(raw, Mapping):
            keys = list(owner.data.keys())
        elif iterable(raw):
            keys = range(len(raw))
        else:
            return
        for key in keys:
            child = owner.__children_get(key)
            if isinstance(child, jsoncDict):
                self.__loads_normalize_slash_dash(child)

    def __loads_is_item(self, container: ts.Node, node: ts.Node) -> bool:
        """Check whether a child node represents a real container item, not a comment."""
        if not node.is_named or node.type == "comment":
            return False
        return node.type == "pair" if container.type == "object" else True

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

    def __loads_pair_slots(
        self, node: ts.Node
    ) -> tuple[ts.Node, ts.Node | None, ts.Node | None]:
        """Return the key, colon, and value nodes for one object pair."""
        key = node.child_by_field_name("key")
        value = node.child_by_field_name("value")
        colon = next((child for child in node.children if child.type == ":"), None)
        if key is None or colon is None:
            raise ValueError(f"unsupported json object pair node: {node}")
        return key, colon, value

    def __loads_collect_pair_comment(
        self,
        owner: Self,
        key: Any,
        slot: _Type_kvSlot,
        text: str,
    ) -> None:
        """Store one pair-internal comment at the proper `Within(key)` slot."""
        if not text:
            return
        current = owner.comments.get(Within(key))
        if current is None:
            slots: dict[jsoncDict._Type_kvSlot, str] = {}
        elif isinstance(current, Mapping):
            slots = cast(dict[jsoncDict._Type_kvSlot, str], dict(current))
        else:
            # Backward-compat for legacy runtime state that still stores a raw string.
            slots = {Within(":", "v"): cast(str, current)}
        slots[slot] = slots.get(slot, "") + text
        owner.comments[Within(key)] = slots

    def __loads_collect_inner_comment(
        self,
        owner: Self,
        node: ts.Node,
        comment: ts.Node,
        byte: bytes,
    ) -> bool:
        """Capture one pair comment when it lives inside the pair node."""
        if node.type != "pair" or comment.type != "comment":
            return False
        key_node, colon, value = self.__loads_pair_slots(node)
        key = self.__key_from_serialized(owner, self.__loads_pair_key(node))
        text = byte[comment.start_byte : comment.end_byte].decode()
        if comment.end_byte <= colon.start_byte:
            self.__loads_collect_pair_comment(owner, key, Within("k", ":"), text)
            return True
        if value is not None and comment.start_byte >= value.start_byte:
            self.__loads_collect_pair_comment(owner, key, Within("v", ","), text)
            return True
        if value is None or comment.end_byte <= value.start_byte:
            self.__loads_collect_pair_comment(owner, key, Within(":", "v"), text)
            return True
        return False

    def __loads_consume_pending_as_value_tail(
        self,
        owner: Self,
        prev_item: ts.Node | None,
        prev_key: Any,
        next_item: ts.Node | None,
        text: str,
    ) -> bool:
        """Reclassify comment runs after an object pair value into its `v,` slot."""
        if (
            prev_item is None
            or prev_item.type != "pair"
            or prev_key is NONE
            or not text
        ):
            return False
        _, _, value = self.__loads_pair_slots(prev_item)
        if value is None:
            return False
        next_start = next_item.start_byte if next_item is not None else None
        if next_start is not None and next_start < value.end_byte:
            return False
        if next_start is not None and next_start < prev_item.end_byte:
            return False
        self.__loads_collect_pair_comment(owner, prev_key, Within("v", ","), text)
        return True

    def __loads_walk_container(
        self, owner: Self, container: ts.Node, byte: bytes
    ) -> None:
        """Walk one parsed object/array and assign surrounding comments to logical slots."""
        prev_key = NONE
        prev_item: ts.Node | None = None
        pending_start: int | None = None
        pending_end: int | None = None
        index = 0
        saw_comma_after_prev = False

        for child in container.children:
            if child.type == "comment":
                if pending_start is None:
                    pending_start = child.start_byte
                pending_end = child.end_byte
                continue
            if child.type == ",":
                if (
                    pending_start is not None
                    and pending_end is not None
                    and container.type == "object"
                    and not saw_comma_after_prev
                ):
                    text = byte[pending_start:pending_end].decode()
                    if self.__loads_consume_pending_as_value_tail(
                        owner, prev_item, prev_key, None, text
                    ):
                        pending_start = pending_end = None
                saw_comma_after_prev = True
                continue
            if not self.__loads_is_item(container, child):
                continue

            # Object items use parsed keys; array items use the running index.
            key = (
                self.__key_from_serialized(owner, self.__loads_pair_key(child))
                if container.type == "object"
                else index
            )
            if pending_start is not None and pending_end is not None:
                text = byte[pending_start:pending_end].decode()
                if text:
                    owner.comments[Within(prev_key, key)] = text
                pending_start = pending_end = None

            if child.type == "pair":
                for pair_child in child.children:
                    if pair_child.type == "comment":
                        self.__loads_collect_inner_comment(
                            owner, child, pair_child, byte
                        )
            # Pair nodes store the nested container under the `value` field.
            value = child.child_by_field_name("value") or child
            if value.type in ("object", "array"):
                child_owner = owner.__children_get(key)
                if isinstance(child_owner, jsoncDict):
                    self.__loads_walk_container(child_owner, value, byte)

            prev_key = key
            prev_item = child
            saw_comma_after_prev = False
            if container.type == "array":
                index += 1

        if pending_start is not None and pending_end is not None:
            text = byte[pending_start:pending_end].decode()
            if not self.__loads_consume_pending_as_value_tail(
                owner, prev_item, prev_key, None, text
            ):
                if text:
                    owner.comments[Within(prev_key, NONE)] = text

    def loads(self, raw: str) -> Self:
        """Bake comment layout hints from `raw` into `self.comments`, `header`, and `footer`."""
        self.__loads_reset_comments(self)
        if not raw:
            return self

        self.__loads_normalize_slash_dash(self)
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
    def dumps(self, obj: Any | None = None, auto_indent: bool | None = None) -> str:
        """Serialize pure data, then restore comments into the emitted JSON text."""
        cls = type(self)
        if auto_indent is not None:
            old_auto_indent = cls.auto_indent
            cls.auto_indent = auto_indent
        try:
            if obj is None:
                obj = self.__dumps_export_value(self, self.data)
            else:
                obj = self.__dumps_export_value(self, obj)
            dump_func = unpack_method(getattr(cls, "_dumps"), cls)
            if dump_func is None:
                raise TypeError(f"{cls.__name__}._dumps is not callable")
            raw = dump_func(obj)
            if not isinstance(raw, str):
                raise TypeError(f"{cls._dumps!r} must return str, got {type(raw)!r}")
            if not (self.comments or self.header or self.footer or self.comments_flat):
                return raw

            byte = raw.encode()
            tree: ts.Tree = self._parser.parse(byte)
            root = tree.root_node
            container = self.__loads_root_container(root)
            if container is None:
                return raw

            edits: list[tuple[int, str]] = []
            self.__dumps_plan_container(self, container, byte, edits)
            if not edits:
                return raw

            out = raw
            for offset, text in sorted(edits, key=lambda item: item[0], reverse=True):
                out = out[:offset] + text + out[offset:]
        finally:
            if auto_indent is not None:
                cls.auto_indent = old_auto_indent
        return out

    def __dumps_export_value(self, owner: Self | None, value: Any) -> Any:
        """Build a dump-ready plain object, applying slash-dash markers from comments."""
        if isinstance(value, jsoncDict):
            owner = value
            value = value.data
        raw = value.v if isinstance(value, sdict) else value

        if isinstance(raw, Mapping):
            out: OrderedDict[Any, Any] = OrderedDict()
            for key, item in raw.items():
                export_key = key
                child_owner = None
                if owner is not None:
                    if key in owner.comments and iterable(item):
                        if not type(self).slash_dash or not isinstance(key, str):
                            raise _TODO
                        export_key = f"/-{key}"
                    child = owner.children.get(key)
                    if child is None and key in owner.data:
                        child = owner.__children_get(key)
                    if isinstance(child, jsoncDict):
                        child_owner = child
                if export_key in out:
                    raise _TODO
                out[export_key] = self.__dumps_export_value(child_owner, item)
            return out

        if iterable(raw):
            out = []
            for index, item in enumerate(raw):
                child_owner = None
                if owner is not None:
                    child = owner.children.get(index)
                    if child is None and index in owner.data:
                        child = owner.__children_get(index)
                    if isinstance(child, jsoncDict):
                        child_owner = child
                out.append(self.__dumps_export_value(child_owner, item))
            return out

        return raw

    def __dumps_container_indent(self, byte: bytes, offset: int) -> str:
        """Return the current line indentation at `offset`."""
        line_start = byte.rfind(b"\n", 0, offset)
        if line_start < 0:
            line_start = 0
        else:
            line_start += 1
        i = line_start
        while i < len(byte) and chr(byte[i]) in (" ", "\t"):
            i += 1
        return byte[line_start:i].decode()

    def __dumps_line_start(self, byte: bytes, offset: int) -> int:
        """Return the byte offset of the current line start."""
        line_start = byte.rfind(b"\n", 0, offset)
        return 0 if line_start < 0 else line_start + 1

    def __dumps_is_line_start(self, byte: bytes, offset: int) -> bool:
        """Check whether `offset` sits at the first non-space column of its line."""
        line_start = byte.rfind(b"\n", 0, offset)
        if line_start < 0:
            line_start = 0
        else:
            line_start += 1
        return all(chr(ch) in (" ", "\t") for ch in byte[line_start:offset])

    def __dumps_format_between_comment(
        self, byte: bytes, offset: int, comment: str, indent: str
    ) -> str:
        """Format a between-item comment block around the current item indentation."""
        text = self._dumps_add_indent(comment, indent)
        if self.__dumps_is_line_start(byte, offset):
            return indent + text + "\n"
        return "\n" + indent + text + "\n"

    def __dumps_format_inline_comment(
        self, comment: str, indent: str, *, suffix_space: bool = False
    ) -> str:
        """Format one inline pair-slot comment with minimal spacing."""
        text = self._dumps_add_indent(comment, indent)
        if "\n" in text:
            return " " + text + (" " if suffix_space else "")
        return " " + text + (" " if suffix_space else "")

    def __dumps_pair_slot_comments(
        self, owner: Self, key: Any
    ) -> dict[_Type_kvSlot, str]:
        """Read normalized slot comments for one object key."""
        comment = owner.comments.get(Within(key))
        if comment is None:
            return {}
        if isinstance(comment, Mapping):
            return cast(dict[jsoncDict._Type_kvSlot, str], dict(comment))
        return {Within(":", "v"): cast(str, comment)}

    def __dumps_plan_pair_comments(
        self,
        owner: Self,
        pair: ts.Node,
        key: Any,
        byte: bytes,
        edits: list[tuple[int, str]],
    ) -> None:
        """Plan intra-pair comment insertions for one object item."""
        slots = self.__dumps_pair_slot_comments(owner, key)
        if not slots:
            return
        _, colon, value = self.__loads_pair_slots(pair)
        indent = self.__dumps_container_indent(byte, pair.start_byte)
        if comment := slots.get(Within("k", ":")):
            edits.append(
                (
                    colon.start_byte,
                    self.__dumps_format_inline_comment(
                        comment, indent, suffix_space=True
                    ),
                )
            )
        if comment := slots.get(Within(":", "v")):
            target = value.start_byte if value is not None else colon.end_byte
            edits.append(
                (
                    target,
                    self.__dumps_format_inline_comment(
                        comment, indent, suffix_space=True
                    ),
                )
            )
        if comment := slots.get(Within("v", ",")):
            target = value.end_byte if value is not None else pair.end_byte
            edits.append(
                (
                    target,
                    self.__dumps_format_inline_comment(comment, indent),
                )
            )

    def __dumps_plan_container(
        self,
        owner: Self,
        container: ts.Node,
        byte: bytes,
        edits: list[tuple[int, str]],
    ) -> None:
        """Walk one serialized container and queue all comment restorations."""
        items = [
            child
            for child in container.children
            if self.__loads_is_item(container, child)
        ]
        prev_key = NONE

        for index, item in enumerate(items):
            key = (
                self.__key_from_serialized(owner, self.__loads_pair_key(item))
                if container.type == "object"
                else index
            )
            if comment := owner.comments.get(Within(prev_key, key)):
                indent = self.__dumps_container_indent(byte, item.start_byte)
                edits.append(
                    (
                        self.__dumps_line_start(byte, item.start_byte),
                        self.__dumps_format_between_comment(
                            byte, item.start_byte, cast(str, comment), indent
                        ),
                    )
                )
            if container.type == "object":
                self.__dumps_plan_pair_comments(owner, item, key, byte, edits)
            value = item.child_by_field_name("value") or item
            if value.type in ("object", "array"):
                child_owner = owner.__children_get(key)
                if isinstance(child_owner, jsoncDict):
                    self.__dumps_plan_container(child_owner, value, byte, edits)
            prev_key = key

        if comment := owner.comments.get(Within(prev_key, NONE)):
            close = container.children[-1]
            indent = (
                self.__dumps_container_indent(byte, items[-1].start_byte)
                if items
                else self.__dumps_container_indent(byte, close.start_byte)
            )
            edits.append(
                (
                    self.__dumps_line_start(byte, close.start_byte),
                    self.__dumps_format_between_comment(
                        byte, close.start_byte, cast(str, comment), indent
                    ),
                )
            )

    def _dumps_add_indent(self, comment: str, indent: str) -> str:
        """add indent before comment, used in restore phase"""
        if not type(self).auto_indent or "\n" not in comment:
            return comment
        return comment.replace("\n", "\n" + indent)

    def hidden_keys(self) -> set[Any]:
        """Return runtime-hidden data keys stored in `comments` at the current depth."""
        return {key for key in self.comments if not is_comment(key)}

    def mixed(self, comments: bool = True) -> OrderedDict[Any, Any]:
        """Materialize the current view.

        `comments=True` keeps `Within(...)` items.
        `comments=False` returns a recursive data-only view with runtime-hidden keys removed.
        """
        return OrderedDict(self.items(comments=comments))

    @property
    def comments_flat(self) -> dict[tuple, _Type_comments]:
        """Flatten nested `comments` dicts by `self.data.keypath`.

        Example:
            `{(): root_comments, ("a",): child_comments, ("a", "b"): grandchild_comments}`
        """
        out: dict[tuple, jsoncDict._Type_comments] = {}

        def collect(node: Self) -> None:
            if node.comments:
                out[node.data.keypath] = dict(node.comments)
            for key, _ in node.__data_items():
                child = node.__children_get(key)
                if isinstance(child, jsoncDict):
                    collect(child)

        collect(self)
        return out

    def comments_get(
        self, key: Within, default: Any = UNSET
    ) -> str | dict[_Type_kvSlot, str] | dict[Within, Any] | Any:
        """Query comment metadata by exact key, wildcard, or item-neighborhood.

        Query forms:
            `Within(a, b)`: exact comment lookup.
            `Within(a, Any)`: all two-sided comments whose left side is `a`.
            `Within(Any, b)`: all two-sided comments whose right side is `b`.
            `Within(a)`: exact single-item slot lookup.
            `Within(Any)`: all single-item slot comments.
            `Within(..., key)`: contiguous comment items immediately before `key`.
            `Within(key, ...)`: contiguous comment items immediately after `key`.
        """
        if not is_comment(key):
            raise TypeError(f"{key=} should be Within(...)")

        parts = tuple(key)
        if ... in parts:
            items = list(self.items())
            data_index = next(
                (
                    i
                    for i, (item_key, _) in enumerate(items)
                    if item_key
                    == parts[0 if len(parts) == 1 or parts[0] is not ... else 1]
                ),
                None,
            )
            if data_index is None:
                if default is not UNSET:
                    return default
                raise KeyError(key)

            out: dict[Within, Any] = {}
            if len(parts) == 2 and parts[0] is ...:
                i = data_index - 1
                while i >= 0 and is_comment(items[i][0]):
                    item_key, value = items[i]
                    out[cast(Within, item_key)] = value
                    i -= 1
                return dict(reversed(tuple(out.items())))

            i = data_index + 1
            while i < len(items) and is_comment(items[i][0]):
                item_key, value = items[i]
                out[cast(Within, item_key)] = value
                i += 1
            return out

        if Any in parts:
            out: dict[Within, Any] = {}
            for comment_key, value in self.comments.items():
                if not is_comment(comment_key):
                    continue
                comment_parts = tuple(comment_key)
                if len(comment_parts) != len(parts):
                    continue
                if all(
                    part is Any or part == comment_part
                    for part, comment_part in zip(parts, comment_parts)
                ):
                    out[comment_key] = value
            return out

        if key in self.comments:
            return self.comments[key]
        if default is not UNSET:
            return default
        raise KeyError(key)

    def items(self, comments: bool = True) -> Iterable[tuple[K | Within, V | str | dict]]:  # type: ignore
        """Iterate the current view in display order.

        `comments=True` yields visible data and `Within(...)` items.
        `comments=False` yields only data items, recursively filtering runtime-hidden keys.

        Yields:
            `Within(left, right), str` for between-item comments.
            `key, value` for visible data items.
            `Within(key), dict[_Type_kvSlot, str] | str` for single-item slot comments.
            `Within(last_key, NONE), str` for trailing comments.
        """
        prev_key = NONE
        hidden_keys = self.hidden_keys()

        for key, _ in self.__data_items():
            comment = self.comments.get(Within(prev_key, key))
            if comments and comment is not None:
                yield Within(prev_key, key), comment
            if key in hidden_keys:
                prev_key = key
                continue
            value = self.__children_get(key)
            # `comments=False` exports nested jsoncDict nodes as plain data-only views.
            if not comments and isinstance(value, jsoncDict):
                value = value.mixed(comments=False)
            yield key, value
            comment = self.comments.get(Within(key))
            if comments and comment is not None:
                yield Within(key), comment
            prev_key = key

        comment = self.comments.get(Within(prev_key, NONE))
        if comments and comment is not None:
            yield Within(prev_key, NONE), comment

    def keys(self) -> Iterable[K | Within]:  # type: ignore
        for key, _ in self.items():
            yield key

    def values(self) -> Iterable[V]:  # type: ignore
        for _, value in self.items():
            yield value

    def apply(self) -> Self:
        """Permanently delete runtime-hidden keys in this tree and all children."""
        hidden_keys = self.hidden_keys()
        items = list(self.__data_items())

        for key, _ in items:
            if key in hidden_keys:
                continue
            value = self.__children_get(key)
            if isinstance(value, jsoncDict):
                value.apply()

        delete_keys = [key for key, _ in items if key in hidden_keys]
        if not isinstance(self.data.v, Mapping):
            delete_keys.sort(reverse=True)

        for key in delete_keys:
            del self.data[key]
            self.children.pop(key, None)
            self.comments.pop(key, None)

        self.__children_sync()
        return self

    def __getitem__(self, key):
        if self.is_keypath(key):
            value = self
            for part in key:
                value = value[part]
            return value
        if is_comment(key):
            return self.comments_get(key)
        # Mixed lookup walks comments and data in the same exported iteration order.
        for item_key, value in self.items():
            if item_key == key:
                return value
        raise KeyError(key)

    def __setitem__(self, key, value) -> None:
        if is_comment(key):
            self.comments[key] = value
            return
        if self.is_keypath(key):
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
        if self.is_keypath(key):
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
        count = 0
        prev_key = NONE
        for key, _ in self.__data_items():
            if Within(prev_key, key) in self.comments:
                count += 1
            if key in self.comments:
                prev_key = key
                continue
            count += 1
            if Within(key) in self.comments:
                count += 1
            prev_key = key
        if Within(prev_key, NONE) in self.comments:
            count += 1
        return count

    def __repr__(self) -> str:
        r = repr(self.mixed())
        if r.startswith("OrderedDict("):
            r = r[len("OrderedDict(") : -1]
        return f"{type(self).__name__}({r})"

    @property
    def body(self) -> str:
        return self.dumps()

    @property
    def full(self) -> str:
        """header + body + footer"""
        return self.header + self.body + self.footer

    def __call__(self) -> str:
        """`__call__` may undergo **breaking changes** in the future, based on its most common calling patterns and usage scenarios."""
        return self.full


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
