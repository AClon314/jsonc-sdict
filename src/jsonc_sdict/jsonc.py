#!/bin/env python3
"""
comment-keyname rules:

| Internal key prefix | Means | Restored shape |
| --- | --- | --- |
| `//` | single-line comment, inline mode | **after** current value/comma, stay in line with value |
| `//\\n` | single-line comment, line-above mode | independent line before next key/value |
| `/*` | block comment (default) | **after** comma`,`, stay in line with value |
| `/*\\n` | block comment, line-above mode | independent line before next key/value |
| `/*,` | block comment before comma | placed before comma of current item |
| `/*k` | block comment before key slot | before JSON key token |
| `/*:` | block comment before colon slot | between key and value |
| `/*v` | block comment before value slot | after colon, before value |
| `/-` | slash_dash comment | comments out a whole subtree (KDL-like style) |
```
"""

import json
from dataclasses import dataclass
from functools import cached_property
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence, Iterable
from typing import Any, Unpack, Literal, cast, overload

from jsonc_sdict.share import UNSET, getLogger, iterable, values_of_type
from jsonc_sdict.sdict import sdict, set_item, get_item, unref

Log = getLogger(__name__)
BeforeSep = Literal["", "\n", ",", "k", ":", "v"]
"""k : v , \n"""
before_seps = values_of_type(BeforeSep)


@dataclass
class CommentData:
    prefix: "hjsonDict._CommentPrefix"
    name: str
    before: BeforeSep = ""

    def __str__(self):
        if self.prefix == "/*":
            return f"/*{self.name}*/"
        return f"{self.prefix}{self.name}"


@dataclass
class BakeComment:
    prefix: str
    value: str
    start: int
    end: int
    trail_newline: bool = False


def json_dumps(obj: Any, indent: int | None = 2) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=indent, cls=CompactJSONEncoder)


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

    _Type_CommentPrefix = Literal["/*", "//", "/-"]
    _comment_prefixes = values_of_type(_Type_CommentPrefix)
    _single_comment: tuple[_Type_CommentPrefix, ...] = ("//",)
    """must be ordered longest to shortest for find()"""
    _auto_count = 0
    """for unique keyname gen"""
    _auto_suffix = "-auto"

    _Type_Cached = Literal["body", "data"] | sdict._Type_Cached

    def __init_subclass__(cls) -> None:
        cls._comment_prefixes = values_of_type(cls._Type_CommentPrefix)
        # TODO: sort _single_comment, longest at first

    @overload
    def __init__(
        self,
        raw: Mapping[K, V],
        loads: Callable[[str], Any] | None = None,
        dumps: Callable[[Any], str] = json_dumps,
        slash_dash: bool = True,
        auto_indent: bool = True,
        has_comment: bool = True,
        **kwargs: Unpack[sdict.Kwargs],
    ): ...

    @overload
    def __init__(
        self,
        raw: str,
        loads: Callable[[str], Any],
        dumps: Callable[[Any], str] = json_dumps,
        slash_dash: bool = True,
        auto_indent: bool = True,
        has_comment: bool = True,
        **kwargs: Unpack[sdict.Kwargs],
    ): ...

    def __init__(
        self,
        raw: str | Mapping[K, V],
        loads: Callable[[str], Any] | None = None,
        dumps: Callable[[Any], str] = json_dumps,
        slash_dash: bool = True,
        auto_indent: bool = True,
        has_comment: bool = True,
        **kwargs: Unpack[sdict.Kwargs],
    ):
        """
        Args:
            raw: text with comment
            loads: callable & able to parse `.jsonc` at least, to parse raw text, eg: `hjson.loads`
                **required** when `raw` is str
            dumps: same as `loads`
            slash_dash: if key_name starts_with `/-`, like `/-mynode` will comment the whole tree node, see [kdl](https://kdl.dev/) config style
            has_comment:
                False: treat **all comment_prefix keys as data key, not comment** key, by **recorded in `self.forceDataKeys`**. Or you promise there's no comment key.
                True: if key name satisfy the comment-keyname rule, do nothing internally.
            **kwargs: see `sdict()`
        """
        self._loads_raw = loads
        self._dumps_raw = dumps
        self.slash_dash = slash_dash
        """if key_name starts_with `/-`, like `/-mynode` will comment the whole tree node, see [kdl](https://kdl.dev/) config style"""

        self.auto_indent = auto_indent
        """mainly for multi-line comment. if False, then you need manually handle indent"""

        self.header, self.footer = "", ""
        self.bodyEdge = None, None
        self.forceDataKeys: set[str | tuple[str, ...]] = set()
        if not slash_dash:
            styles = list(self._comment_prefixes)
            styles.remove("/-")
            self._comment_prefixes = tuple(styles)

        if isinstance(raw, str):
            if has_comment is None:
                has_comment = True
            data = self.loads_raw(raw)
            # data(dict): have un-converted comments, miss raw's comments
            # raw(str): have comments & data raw info
        else:
            if has_comment is None:
                has_comment = True
            data = raw
            raw = ""
            # data(dict): have un-converted comments
            # raw(str): empty
        # 其实raw(str)并不重要，我们只关心data(dict)
        # `sdict.__init__` may call `self.__setitem__`, so setup attrs before this call.
        super().__init__(data, **kwargs)
        self.loads(raw, has_comment=has_comment)

    def loads_raw(self, raw: str) -> Any:
        """`loads` from `__init__`, should be able to parse .jsonc at least"""
        try:
            return self._loads_raw(raw)  # type: ignore
        except Exception as e:
            raise TypeError(
                f"{self._loads_raw=} should be callable & can parse .jsonc at least, example: `hjson.loads`"
            ) from e

    def dumps_raw(self, obj: Any) -> str:
        return self._dumps_raw(obj)

    @classmethod
    def split_key(cls, key: str | Any) -> CommentData | None:
        """return CommentData if is comment, else None"""
        if not (isinstance(key, str)):
            return
        for prefix in cls._comment_prefixes:
            if key.startswith(prefix):
                sep = cast(BeforeSep, key[len(prefix)])
                # single-comment only 2 modes: `//` and `//\n` (or `#` and `#\n`)
                reset_single = prefix in cls._single_comment and sep != "\n"
                if reset_single or sep not in before_seps or prefix == "/-":
                    sep = ""
                return CommentData(prefix=prefix, before=sep, name=key[len(prefix) :])

    is_comment = split_key

    def _match_single_comment_prefix(self, text: str, idx: int) -> str | None:
        for prefix in self._single_comment:
            if text.startswith(prefix, idx):
                return prefix
        return None

    def _add_indent(self, comment: str, indent: str) -> str:
        """add indent before comment, used in restore phase"""
        if not self.auto_indent or "\n" not in comment:
            return comment
        return comment.replace("\n", "\n" + indent)

    def _restore_comment(
        self, comment: CommentData | str, value: Any = "", indent: str = ""
    ):
        """used in restore phase"""
        prefix = comment.prefix if isinstance(comment, CommentData) else str(comment)
        val = value if isinstance(value, str) else self.dumps_raw(value)
        if any(prefix.startswith(single) for single in self._single_comment):
            val = val.rstrip("\n")
        val = self._add_indent(val, indent)

        if prefix.startswith("/*"):
            return f"/*{val}*/"
        for single in self._single_comment:
            if prefix.startswith(single):
                return f"{single}{val}"
        return f"{prefix}{val}"

    def _is_list_comment_item(self, value: Any) -> tuple[CommentData, Any] | None:
        if not isinstance(value, Mapping) or len(value) != 1:
            return None
        ((k, val),) = value.items()
        parts = self.split_key(k)
        if parts is None:
            return None
        if parts.prefix == "/-":
            return None
        return parts, val

    def _find_root_start(self, n: int, code: str) -> int:
        i = 0
        in_str = False
        escaped = False
        while i < n:
            c = code[i]
            if in_str:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    in_str = False
                i += 1
                continue
            if c == '"':
                in_str = True
                i += 1
                continue
            if c in "{[":
                return i
            i += 1
        raise ValueError("bodyEdge NOT found, json must have {} or [] as root")

    @property
    def _autoKey(self):
        return f"{self._auto_count}{self._auto_suffix}"

    def _new_autoKey(self, prefix: _Type_CommentPrefix) -> CommentData:
        name = f"{self._autoKey}"
        self._auto_count += 1
        return CommentData(prefix=prefix, name=name)

    def loads(self, raw="", has_comment: bool = False) -> Mapping:
        """bake `self` dict with `raw` hint"""
        if has_comment and not raw:
            return self
        raw = raw.replace("\r", "")
        # n = len(raw)
        # comment_index = 0
        for obj in self.dfs():
            if isinstance(obj.v, Mapping):
                for key in list(obj.keys()):
                    comment = self.split_key(key)
                    if not comment:
                        continue
                    comment
            else:  # iterable
                for v in obj.v:
                    pass

        def append_obj_comment(obj: OrderedDict, prefix: str, value: str):
            obj[str(self._new_autoKey(prefix))] = value

        def append_list_comment(arr: list, prefix: str, value: str):
            arr.append({str(self._new_autoKey(prefix)): value})

        def line_start(pos: int) -> int:
            return raw.rfind("\n", 0, pos) + 1

        def line_end(pos: int) -> int:
            j = raw.find("\n", pos)
            return n if j < 0 else j

        def has_code_before_on_line(pos: int) -> bool:
            return any(not ch.isspace() for ch in code[line_start(pos) : pos])

        def has_code_after_on_line(pos: int) -> bool:
            return any(not ch.isspace() for ch in code[pos : line_end(pos)])

        def scan_comments(text: str) -> tuple[str, list[BakeComment]]:
            chars = list(text)
            tokens: list[BakeComment] = []
            i = 0
            in_str = False
            escaped = False
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
                if c == '"':
                    in_str = True
                    i += 1
                    continue
                single_prefix = self._match_single_comment_prefix(text, i)
                if single_prefix is not None:
                    start = i
                    i += len(single_prefix)
                    body_start = i
                    while i < n and text[i] != "\n":
                        i += 1
                    end = i
                    newline = i < n and text[i] == "\n"
                    tokens.append(
                        BakeComment(
                            prefix=single_prefix,
                            value=text[body_start:end],
                            start=start,
                            end=end,
                            trail_newline=newline,
                        )
                    )
                    for j in range(start, end):
                        chars[j] = " "
                    continue
                if text.startswith("/*", i):
                    start = i
                    body_start = i + 2
                    mark = text.find("*/", body_start)
                    if mark < 0:
                        raise ValueError("unterminated block comment")
                    end = mark + 2
                    tokens.append(
                        BakeComment(
                            prefix="/*",
                            value=text[body_start:mark],
                            start=start,
                            end=end,
                        )
                    )
                    for j in range(start, end):
                        if chars[j] != "\n":
                            chars[j] = " "
                    i = end
                    continue
                i += 1
            return "".join(chars), tokens

        def skip_ws(pos: int, end: int | None = None) -> int:
            limit = n if end is None else end
            while pos < limit and code[pos].isspace():
                pos += 1
            return pos

        def find_container_end(start: int) -> int:
            open_ch = code[start]
            close_ch = "}" if open_ch == "{" else "]"
            depth = 1
            i = start + 1
            in_str = False
            escaped = False
            while i < n:
                c = code[i]
                if in_str:
                    if escaped:
                        escaped = False
                    elif c == "\\":
                        escaped = True
                    elif c == '"':
                        in_str = False
                    i += 1
                    continue
                if c == '"':
                    in_str = True
                    i += 1
                    continue
                if c == open_ch:
                    depth += 1
                elif c == close_ch:
                    depth -= 1
                    if depth == 0:
                        return i + 1
                i += 1
            raise ValueError(f"unterminated container that starts at index {start}")

        def pop_comments(left: int, right: int) -> list[BakeComment]:
            nonlocal comment_index
            out: list[BakeComment] = []
            while comment_index < len(comments) and comments[comment_index].end <= left:
                comment_index += 1
            while comment_index < len(comments):
                token = comments[comment_index]
                if token.start >= right:
                    break
                if token.end <= right:
                    out.append(token)
                    comment_index += 1
                    continue
                break
            return out

        def find_key_in_object(key: str, cursor: int, close: int) -> int:
            key_token = self.dumps_raw(key)
            search = cursor
            while True:
                pos = code.find(key_token, search, close)
                if pos < 0:
                    raise ValueError(f"key {key!r} not found near index {cursor}")
                after_key = skip_ws(pos + len(key_token), close)
                if after_key < close and code[after_key] == ":":
                    return pos
                search = pos + 1

        def find_scalar_end(start: int, close: int) -> int:
            if start >= close:
                raise ValueError("unexpected EOF while parsing scalar value")
            if code[start] == '"':
                i = start + 1
                escaped = False
                while i < close:
                    c = code[i]
                    if escaped:
                        escaped = False
                    elif c == "\\":
                        escaped = True
                    elif c == '"':
                        return i + 1
                    i += 1
                raise ValueError("unterminated string value")
            i = start
            while i < close and code[i] not in ",}]":
                i += 1
            while i > start and code[i - 1].isspace():
                i -= 1
            return i

        def next_sig_char(pos: int, close: int) -> str:
            j = skip_ws(pos, close)
            return "" if j >= close else code[j]

        def prev_sig_char(pos: int, start: int) -> str:
            j = pos - 1
            while j >= start:
                if code[j].isspace():
                    j -= 1
                    continue
                return code[j]
            return ""

        def emit_obj_comments(
            obj: OrderedDict,
            tokens: list[BakeComment],
            mode: Literal["before_key", "before_colon", "before_value", "after_value"],
            start: int,
            close: int,
        ):
            for token in tokens:
                if token.prefix == "/*":
                    if mode == "before_colon":
                        prefix = "/*:"
                    elif mode == "before_value":
                        prefix = "/*v"
                    elif mode == "after_value":
                        prefix = (
                            "/*," if next_sig_char(token.end, close) == "," else "/*\n"
                        )
                    else:
                        prev_sig = prev_sig_char(token.start, start)
                        line_only = (not has_code_before_on_line(token.start)) and (
                            not has_code_after_on_line(token.end)
                        )
                        at_line_tail_after_comma = (
                            prev_sig == "," and not has_code_after_on_line(token.end)
                        )
                        prefix = (
                            "/*\n" if (line_only or at_line_tail_after_comma) else "/*k"
                        )
                    append_obj_comment(obj, prefix, token.value)
                    continue
                line_above = mode == "before_key" and (
                    not has_code_before_on_line(token.start)
                )
                if mode == "after_value" and not has_code_before_on_line(token.start):
                    line_above = True
                prefix = token.prefix + ("\n" if line_above else "")
                value = token.value
                append_obj_comment(obj, prefix, value)

        def emit_array_comments(
            arr: list[Any],
            tokens: list[BakeComment],
            mode: Literal["before_value", "after_value"],
        ):
            for token in tokens:
                if token.prefix == "/*":
                    if mode == "before_value":
                        line_only = (not has_code_before_on_line(token.start)) and (
                            not has_code_after_on_line(token.end)
                        )
                        prefix = "/*\n" if line_only else "/*"
                    else:
                        prefix = "/*"
                    append_list_comment(arr, prefix, token.value)
                    continue
                line_above = mode == "before_value" and (
                    not has_code_before_on_line(token.start)
                )
                prefix = token.prefix + ("\n" if line_above else "")
                value = token.value
                append_list_comment(arr, prefix, value)

        def parse_value(node: Any, start: int, close: int):
            pos = skip_ws(start, close)
            if isinstance(node, Mapping):
                return parse_object(node, pos, close)
            if iterable(node):
                return parse_array(node, pos, close)
            end = find_scalar_end(pos, close)
            return node, end

        def parse_object(node: Mapping[str, Any], start: int, close: int):
            if start >= close or code[start] != "{":
                raise ValueError(f"expected '{{' at index {start}")
            end = find_container_end(start)
            end_close = end - 1
            obj: OrderedDict[str, Any] = OrderedDict()
            cursor = start + 1

            for key, node_val in node.items():
                if not isinstance(key, str):
                    raise TypeError(f"object key must be str, got {type(key)!r}")
                key_pos = find_key_in_object(key, cursor, end_close)
                emit_obj_comments(
                    obj,
                    pop_comments(cursor, key_pos),
                    mode="before_key",
                    start=start + 1,
                    close=end_close,
                )

                key_token = self.dumps_raw(key)
                key_end = key_pos + len(key_token)
                colon_pos = skip_ws(key_end, end_close)
                emit_obj_comments(
                    obj,
                    pop_comments(key_end, colon_pos),
                    mode="before_colon",
                    start=start + 1,
                    close=end_close,
                )
                if colon_pos >= end_close or code[colon_pos] != ":":
                    raise ValueError(f"expected ':' after key {key!r}")

                value_pos = skip_ws(colon_pos + 1, end_close)
                emit_obj_comments(
                    obj,
                    pop_comments(colon_pos + 1, value_pos),
                    mode="before_value",
                    start=start + 1,
                    close=end_close,
                )
                parsed_val, value_end = parse_value(node_val, value_pos, end_close)
                obj[key] = parsed_val

                delim_pos = skip_ws(value_end, end_close)
                emit_obj_comments(
                    obj,
                    pop_comments(value_end, delim_pos),
                    mode="after_value",
                    start=start + 1,
                    close=end_close,
                )
                if delim_pos < end_close and code[delim_pos] == ",":
                    cursor = delim_pos + 1
                else:
                    cursor = delim_pos

            emit_obj_comments(
                obj,
                pop_comments(cursor, end_close),
                mode="before_key",
                start=start + 1,
                close=end_close,
            )
            return obj, end

        def parse_array(node: Iterable[Any], start: int, close: int):
            if start >= close or code[start] != "[":
                raise ValueError(f"expected '[' at index {start}")
            end = find_container_end(start)
            end_close = end - 1
            arr: list[Any] = []
            cursor = start + 1

            for item in node:
                value_pos = skip_ws(cursor, end_close)
                emit_array_comments(
                    arr, pop_comments(cursor, value_pos), "before_value"
                )
                parsed_item, value_end = parse_value(item, value_pos, end_close)
                arr.append(parsed_item)

                delim_pos = skip_ws(value_end, end_close)
                emit_array_comments(
                    arr, pop_comments(value_end, delim_pos), "after_value"
                )
                if delim_pos < end_close and code[delim_pos] == ",":
                    cursor = delim_pos + 1
                else:
                    cursor = delim_pos

            emit_array_comments(arr, pop_comments(cursor, end_close), "before_value")
            return arr, end

        code, comments = scan_comments(raw)
        src_start = self._find_root_start(n, code)
        src_end = find_container_end(src_start)

        root_data = unref(self.v)
        if (
            (not root_data)
            or (code[src_start] == "{" and not isinstance(root_data, Mapping))
            or (code[src_start] == "[" and not iterable(root_data))
        ):
            try:
                root_data = json.loads(
                    code[src_start:src_end], object_pairs_hook=OrderedDict
                )
            except json.JSONDecodeError:
                if code[src_start] == "{":
                    root_data = OrderedDict()
                else:
                    root_data = []

        while (
            comment_index < len(comments) and comments[comment_index].end <= src_start
        ):
            comment_index += 1

        root, parsed_end = parse_value(root_data, src_start, src_end)
        if parsed_end < src_end:
            if isinstance(root, list):
                emit_array_comments(
                    root, pop_comments(parsed_end, src_end), "before_value"
                )
            elif isinstance(root, Mapping):
                emit_obj_comments(
                    cast(OrderedDict, root),
                    pop_comments(parsed_end, src_end),
                    mode="before_key",
                    start=src_start + 1,
                    close=src_end - 1,
                )

        body = self.dumps_raw(root)
        self.bodyEdge = src_start, src_end
        self.header = raw[:src_start]
        self.footer = raw[src_end:]
        self.clear()
        self.update(root)
        self.rebuild()
        return body

    def dumps(self, obj: Any | None = None, depth=0) -> str:
        """restore"""
        if obj is None:
            obj = self.v
        obj = unref(obj)
        inner = self.dumps_raw(obj)
        # TODO: implement this

        return out

    @cached_property
    def data(self):
        """data only, no comment"""
        # TODO
        return

    @cached_property
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

    @classmethod
    def _is_after(cls, c: CommentData) -> bool:
        single = c.prefix == "//" and not c.before
        multi = c.prefix == "/*" and c.before == "\n"
        return single or multi

    def insert(
        self,
        update: Mapping,
        key: K | UNSET = UNSET,
        index: int | None = None,
        after=False,
        has_comment=True,
    ):
        """
        insert the `update` dict before `key` or `index`

        Args:
            has_comment: if set to `False`, treat **all keys as dataKeys** forcibly, recorded by `self.forcedataKeys`

        Raises:
            KeyError: raise if any of comments's keys already in `self.forcedataKeys`.
                Suggest use another keyname.

        comment-keyname rules:

        | Internal key prefix | Means | Restored shape |
        | --- | --- | --- |
        | `//` | single-line comment, inline mode | **after** current value/comma, stay in line with value |
        | `//\\n` | single-line comment, line-above mode | independent line before next key/value |
        | `/*` | block comment (default) | **after** comma`,`, stay in line with value |
        | `/*\\n` | block comment, line-above mode | independent line before next key/value |
        | `/*,` | block comment before comma | placed before comma of current item |
        | `/*k` | block comment before key slot | before JSON key token |
        | `/*:` | block comment before colon slot | between key and value |
        | `/*v` | block comment before value slot | after colon, before value |
        | `/-` | slash_dash comment | comments out a whole subtree (KDL-like style) |
        """
        if has_comment:
            comments = {
                k for k in update if self.split_key(k) and k in self.forceDataKeys
            }
            if comments:
                raise KeyError(
                    f"keys of {comments=} already existed in `self.forcedataKeys`"
                )

            # only re-order the last continuous comments
            # eg: {comments_A, data, comments_B}, then only re-order comments_B
            # find the key: {comments_A, data...data_end, //, /*\n(commentEnd_start), comments_B}
            data_end = UNSET
            commentEnd_start = UNSET
            for k in reversed(update):
                cKey = self.split_key(k)
                if cKey:
                    if commentEnd_start is UNSET and self._is_after(cKey):
                        commentEnd_start = k
                    else:
                        commentEnd_start = UNSET
                else:
                    data_end = k
                    break
            if commentEnd_start is UNSET:
                if data_end is UNSET:
                    # update dict is empty
                    return
                # all data
                start_key = data_end
            else:
                # all comments, or comments_B founded
                start_key = commentEnd_start

            collect = False
            comments = {}
            for k in update:
                if not collect and k == start_key:
                    collect = True
                    continue
                if collect:
                    comments[k] = self.split_key(k)

            after = {k: update[k] for k, v in comments.items() if self._is_after(v)}
            before = {k: update[k] for k, v in comments.items() if k not in after}
            update = {k: v for k, v in update.items() if k not in comments}
            super().insert(update, key, index, after)
            super().insert(before, key, index, after=False)
            super().insert(after, key, index, after=True)
        else:
            self.forceDataKeys.update({k for k in update if self.split_key(k)})
            super().insert(update, key, index, after)

    def comment_out(self, values: Iterable | None = None):
        """
        Usage:
        ```python
        jc[key0, key1].comment_out() # to slash_dash comment `/-`
        jc[key0, key1].comment_out([1,2]) # only comment value 1,2 as `/* 1, 2 */`
        ```
        """
        # TODO: implement this in the future
        if values is None:
            self.rename_key(new=f"/-{self.keypaths[-1][-1]}")
            return
        is_list = iterable(self.v)
        for v in values:
            for k in self.v_to_k(v):
                if is_list:
                    pass  # TODO: value → {"/*counterSEED": value}
                else:
                    self.rename_key(k, "/*counterSEED")


class hjsonDict[K = str, V = Any](jsoncDict[K, V]):
    _CommentPrefix = Literal["/*", "//", "#", "/-"]
    _single_comment: tuple[_CommentPrefix, ...] = ("//", "#")

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
            single_prefix = self._match_single_comment_prefix(text, i)
            if single_prefix is not None:
                in_line = True
                i += len(single_prefix)
                continue
            return c, i
        return None, -1

    def load(self, raw: str) -> str:
        first, _ = self._first_significant_char(raw)
        rootless_object = first not in ("{", "[", None) and isinstance(self.v, Mapping)
        self._rootless_object = rootless_object
        if not rootless_object:
            return super().loads(raw)

        wrapped = "{\n" + raw + "\n}"
        body = super().loads(wrapped)
        self.header = ""
        self.footer = ""
        self.bodyEdge = 0, len(raw)
        return body

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


Type_jsonc = jsoncDict | type[jsoncDict]


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
