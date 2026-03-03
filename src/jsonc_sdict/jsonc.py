#!/bin/env python3
"""
comment-keyname rules:

| Internal key prefix | Means | Restored shape |
| --- | --- | --- |
| `//` | single-line comment, inline mode | after current value/comma |
| `//\n` | single-line comment, line-above mode | independent line before next key/value |
| `/*` | block comment (default) | inline block comment |
| `/*\n` | block comment with trailing newline mode | rendered with line break behavior |
| `/*,` | block comment before comma | placed before comma of current item |
| `/*k` | block comment before key slot | before JSON key token |
| `/*:` | block comment before colon slot | between key and value |
| `/*v` | block comment before value slot | after colon, before value |
| `/-` | node comment | comments out a whole subtree (KDL-like style) |
```
"""

import json
from uuid import uuid4
from dataclasses import dataclass
from functools import cached_property
from collections import OrderedDict
from collections.abc import Mapping, Sequence, Iterable
from typing import Literal, Any, get_args, cast

from jsonc_sdict.share import UNSET, getLogger, iterable
from jsonc_sdict.sdict import sdict, set_item, get_item

Log = getLogger(__name__)
SEED = "-" + uuid4().hex
AS_DATA = "-" + uuid4().hex
"""use with jsonc/hjson like `"//your data key overlap with comment-keyname rule?" + AS_DATA: ["treat as data, not comment"]`"""
BeforeSep = Literal["", "\n", ",", "k", ":", "v"]
"""k : v , \n"""
before_seps: tuple[BeforeSep] = get_args(BeforeSep)


@dataclass
class CommentData:
    prefix: "hjson._CommentPrefix"
    keyname: str
    before: BeforeSep = ""

    def __str__(self):
        if self.prefix == "/*":
            return f"/*{self.keyname}*/"
        return f"{self.prefix}{self.keyname}"


@dataclass
class BakeComment:
    prefix: str
    value: str
    start: int
    end: int
    has_trailing_newline: bool = False


class jsonc[K = str, V = Any](sdict[K, V]):
    """
    ### Usage
    life cycle: jc.bake() → 3rd-party lib json.loads(body) → jc.update() → user's jc.insert_comment() → jc.full from restore()
    ```python
    jc = jsonc(my_dict) # or jsonc(json.loads(my_str), my_str)
    # jc.update(hjson.loads(jc.body)) # if my_str
    jc["//unique-keyname"] = "my comment but at end of body"
    jc.insert_comment({
        "/*\\nunique-keyname-1": "my multi-\\nline comments\\n"
        "//\\nunique-keyname-2": "my line-above comments"
        "//your data key overlap with comment-keyname rule?" + AS_DATA: ["treat as data, not comment"] # rare edge case
        }, "existedKey"
    )
    jc.body = hjson.dumps(jc)
    f.write(jc.body)
    ```
    """

    _CommentPrefix = Literal["/*", "//", "/-"]
    _comment_prefixes: tuple[_CommentPrefix, ...] = get_args(_CommentPrefix)
    _single_comment: tuple[_CommentPrefix, ...] = ("//",)

    def __init_subclass__(cls) -> None:
        cls._comment_prefixes = get_args(cls._CommentPrefix)

    def __init__(
        self,
        map: Mapping[K, V] | None = None,
        raw: str | None = None,
        seed: str = SEED,
        node_comment=True,
        auto_indent=True,
        identify_commentKey=True,
        **kwargs,
    ):
        """
        Args:
            map (dict): if `raw` is provided, then `map` should be parser-output without comments (e.g. `json.loads(stripped_raw)`), so `bake()` can use structure context.
            raw: text with comment
            seed: use uuid4.hex as suffix, ensures consistent global uuid-seed per Python startup
            node_comment: if key_name starts_with `/-`, like `/-mynode` will comment the whole tree node, see [kdl](https://kdl.dev/) style
            identify_commentKey: if you ensure there's no key starts_with `/`, or you want treated all comment_prefix key as real data, you can set `False`, and it can be faster.
            **kwargs: see `sdict()`
        """
        self.SEED = seed
        """should const & readonly, do NOT modify this"""
        self.auto_indent = auto_indent
        """mainly for multi-line comment. if False, then you need manually handle indent"""

        self.header, self.footer = "", ""
        self.bodyEdge = None, None
        if not node_comment:
            styles = list(self._comment_prefixes)
            styles.remove("/-")
            self._comment_prefixes = tuple(styles)  # type: ignore

        # `sdict.__init__` may call `self.__setitem__`, so setup attrs before this call.
        super().__init__(map or {}, **kwargs)
        if identify_commentKey:
            raw = self.to_inner_key_batch(raw)
        if raw is not None:
            self.bake(raw)

    def split_keyname(self, keyname: Any) -> CommentData | None:
        """
        return comment key parts if is comment, else None
        """
        if not (isinstance(keyname, str) and keyname.endswith(self.SEED)):
            return None
        no_seed = keyname[: -len(self.SEED)]
        for prefix in self._comment_prefixes:
            if no_seed.startswith(prefix):
                sep = no_seed[len(prefix)]
                # single-comment only 2 modes: `//` and `//\n` (or `#` and `#\n`)
                reset_single = prefix in self._single_comment and sep != "\n"
                if reset_single or sep not in before_seps or prefix == "/-":
                    sep = ""
                return CommentData(
                    prefix=prefix, before=sep, keyname=no_seed[len(prefix) :]
                )
        raise ValueError(f"invalid comment prefix of {keyname=}")

    def is_comment(self, keyname: Any) -> str:
        parts = self.split_keyname(keyname)
        return "" if parts is None else str(parts)

    def to_inner_key_batch(self, raw: str | None = None) -> str | None:
        """
        deep convert existedKey that start_with `/` (comment_prefix), by add `SEED` suffix, used at init phase before bake()
        Args:
            raw: to sync inner key change, raw is **required**
        Returns:
            raw: added SEED as suffix
        """

        def _replace_raw_key_token(
            old_key: str, new_key: str, text: str | None
        ) -> str | None:
            if text is None or old_key == new_key:
                return text
            # compability for json5/hjson, if keyname is not in "quote"
            # old_key_token = json.dumps(old_key, ensure_ascii=False)
            # new_key_token = json.dumps(new_key, ensure_ascii=False)
            return text.replace(old_key, new_key)

        def _need_touch(key: Any) -> bool:
            if not isinstance(key, str):
                return False
            if self.to_inner_key(key) != key:
                return True
            if raw is None or not key.endswith(self.SEED):
                return False
            raw_key = key[: -len(self.SEED)]
            return any(raw_key.startswith(prefix) for prefix in self._comment_prefixes)

        for parent in self.dfs(
            yieldIf=lambda parent, _: any(_need_touch(k) for k in parent.keys())
        ):
            for key in tuple(parent.keys()):
                if not isinstance(key, str):
                    continue
                inner_key = self.to_inner_key(key)
                if inner_key != key:
                    parent.rename_key(key, inner_key, deep=False)
                    raw = _replace_raw_key_token(key, inner_key, raw)
                    key = inner_key
                if key.endswith(self.SEED):
                    raw_key = key[: -len(self.SEED)]
                    if any(
                        raw_key.startswith(prefix) for prefix in self._comment_prefixes
                    ):
                        raw = _replace_raw_key_token(raw_key, key, raw)
        return raw

    def _single_prefixes_sorted(self) -> tuple[str, ...]:
        return tuple(sorted(self._single_comment, key=len, reverse=True))

    def _match_single_comment_prefix(self, text: str, idx: int) -> str | None:
        for prefix in self._single_prefixes_sorted():
            if text.startswith(prefix, idx):
                return prefix
        return None

    def _add_indent(self, comment: str, indent: str) -> str:
        """add indent before comment, used in restore phase"""
        if not self.auto_indent or "\n" not in comment:
            return comment
        return comment.replace("\n", "\n" + indent)

    def restore_comment(
        self, comment: CommentData | str, value: Any = "", indent: str = ""
    ):
        """used in restore phase"""
        prefix = comment.prefix if isinstance(comment, CommentData) else str(comment)
        val = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
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
        parts = self.split_keyname(k)
        if parts is None:
            return None
        if parts.prefix == "/-":
            return None
        return parts, val

    def bake(self, raw: str):
        raw = raw.replace("\r", "")
        n = len(raw)
        counter = 0
        comment_index = 0

        def to_plain(value: Any):
            if isinstance(value, Mapping):
                return OrderedDict((k, to_plain(v)) for k, v in value.items())
            if iterable(value):
                return [to_plain(v) for v in value]
            return value

        def new_comment_key(prefix: str) -> str:
            nonlocal counter
            key = f"{prefix}{counter}{self.SEED}"
            counter += 1
            return key

        def append_obj_comment(obj: OrderedDict, prefix: str, value: str):
            obj[new_comment_key(prefix)] = value

        def append_list_comment(arr: list, prefix: str, value: str):
            arr.append({new_comment_key(prefix): value})

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
                    has_nl = i < n and text[i] == "\n"
                    tokens.append(
                        BakeComment(
                            prefix=single_prefix,
                            value=text[body_start:end],
                            start=start,
                            end=end,
                            has_trailing_newline=has_nl,
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

        def find_root_start() -> int:
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
            key_token = json.dumps(key, ensure_ascii=False)
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

                key_token = json.dumps(key, ensure_ascii=False)
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
        src_start = find_root_start()
        src_end = find_container_end(src_start)

        root_data = to_plain(self.v)
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

        body = json.dumps(root, ensure_ascii=False, indent=2, cls=CompactJSONEncoder)
        self.bodyEdge = src_start, src_end
        self.header = raw[:src_start]
        self.footer = raw[src_end:]
        self._body_cache = body
        return body

    @property
    def body(self) -> str:
        """jc.update(hjson.loads(jc.body)) # ready for loads, comment-alive"""
        return self._body_cache

    @cached_property
    def _body_cache(self) -> str:
        # abstract _body_cache because body.setter
        return json.dumps(self.v, ensure_ascii=False, indent=2, cls=CompactJSONEncoder)

    @body.setter
    def body(self, value: str | Mapping):
        """`jc.body = hjson.dumps(jc)` or `jc.update(hjson.dumps(jc))`"""
        if isinstance(value, str):
            self._body_cache = value
            return
        self.clear()
        self.update(value)
        del self.body

    @body.deleter
    def body(self):
        try:
            del self._body_cache
        except AttributeError as e:
            pass
            # Log.warning(e)

    def restore(self, obj: Mapping | Sequence, depth: int) -> str:
        if isinstance(obj, sdict):
            obj = obj.v
        ind = "  " * depth
        next_ind = "  " * (depth + 1)

        def comment_priority(parts: CommentData) -> int:
            if parts.prefix == "/*":
                return 0
            if parts.prefix in self._single_comment:
                return 1
            if parts.prefix == "/-":
                return 2
            return 3

        def render_bucket(bucket: list[tuple[int, str]]) -> str:
            if not bucket:
                return ""
            ordered = [text for _, text in sorted(bucket, key=lambda x: x[0])]
            return " ".join(ordered)

        if isinstance(obj, Mapping):
            lines = ["{"]
            items = list(obj.items())
            data_total = sum(
                1
                for k, _ in items
                if (parts := self.split_keyname(k)) is None or parts.prefix == "/-"
            )
            data_seen = 0

            pending_line_above: list[str] = []
            pending_before_key: list[str] = []
            pending_before_colon: list[str] = []
            pending_before_value: list[str] = []

            line_base: str | None = None
            line_has_comma = False
            before_comma_comments: list[tuple[int, str]] = []
            after_comma_comments: list[tuple[int, str]] = []

            def flush_line():
                nonlocal \
                    line_base, \
                    line_has_comma, \
                    before_comma_comments, \
                    after_comma_comments
                if line_base is None:
                    return
                line = line_base
                before_text = render_bucket(before_comma_comments)
                if before_text:
                    line += " " + before_text
                if line_has_comma:
                    line += ","
                after_text = render_bucket(after_comma_comments)
                if after_text:
                    line += " " + after_text
                lines.append(line)
                line_base = None
                line_has_comma = False
                before_comma_comments = []
                after_comma_comments = []

            for k, val in items:
                parts = self.split_keyname(k)
                if parts is not None and parts.prefix != "/-":
                    rendered = self.restore_comment(parts, val, next_ind)
                    priority = comment_priority(parts)
                    if parts.before == ",":
                        if line_base is not None:
                            before_comma_comments.append((priority, rendered))
                        else:
                            pending_line_above.append(rendered)
                        continue
                    if parts.before == "\n":
                        if parts.prefix in self._single_comment:
                            pending_line_above.append(rendered)
                        elif line_base is not None:
                            after_comma_comments.append((priority, rendered))
                        else:
                            pending_line_above.append(rendered)
                        continue
                    if parts.before == "k":
                        pending_before_key.append(rendered)
                        continue
                    if parts.before == ":":
                        pending_before_colon.append(rendered)
                        continue
                    if parts.before == "v":
                        pending_before_value.append(rendered)
                        continue
                    if parts.prefix in self._single_comment:
                        if line_base is not None:
                            after_comma_comments.append((priority, rendered))
                        else:
                            pending_line_above.append(rendered)
                    else:
                        pending_before_key.append(rendered)
                    continue

                flush_line()
                for c in pending_line_above:
                    lines.append(f"{next_ind}{c}")
                pending_line_above = []

                data_seen += 1
                has_comma = data_seen < data_total
                if parts is not None and parts.prefix == "/-":
                    out_key = f"{parts.prefix}{parts.keyname}"
                else:
                    out_key = k
                key_text = json.dumps(out_key, ensure_ascii=False)
                value_text = self.restore(val, depth + 1)

                key_side = (
                    (" ".join(pending_before_key) + " ") if pending_before_key else ""
                ) + key_text
                if pending_before_colon:
                    key_side += " " + " ".join(pending_before_colon)
                val_side = (
                    (" " + " ".join(pending_before_value))
                    if pending_before_value
                    else ""
                ) + f" {value_text}"

                line_base = f"{next_ind}{key_side}:{val_side}"
                line_has_comma = has_comma
                pending_before_key = []
                pending_before_colon = []
                pending_before_value = []

            flush_line()
            for c in (
                pending_line_above
                + pending_before_key
                + pending_before_colon
                + pending_before_value
            ):
                lines.append(f"{next_ind}{c}")
            lines.append(f"{ind}}}")
            return "\n".join(lines)

        elif iterable(obj):
            lines = ["["]
            items = list(obj)
            data_total = sum(
                1 for item in items if self._is_list_comment_item(item) is None
            )
            data_seen = 0

            pending_before_item: list[str] = []
            line_base: str | None = None
            line_has_comma = False
            before_comma_comments: list[tuple[int, str]] = []
            after_comma_comments: list[tuple[int, str]] = []

            def flush_item_line():
                nonlocal \
                    line_base, \
                    line_has_comma, \
                    before_comma_comments, \
                    after_comma_comments
                if line_base is None:
                    return
                line = line_base
                before_text = render_bucket(before_comma_comments)
                if before_text:
                    line += " " + before_text
                if line_has_comma:
                    line += ","
                after_text = render_bucket(after_comma_comments)
                if after_text:
                    line += " " + after_text
                lines.append(line)
                line_base = None
                line_has_comma = False
                before_comma_comments = []
                after_comma_comments = []

            for item in items:
                comment = self._is_list_comment_item(item)
                if comment is not None:
                    parts, val = comment
                    rendered = self.restore_comment(parts, val, next_ind)
                    priority = comment_priority(parts)
                    if parts.before == ",":
                        if line_base is not None:
                            before_comma_comments.append((priority, rendered))
                        else:
                            pending_before_item.append(rendered)
                    elif parts.before == "\n":
                        if parts.prefix in self._single_comment:
                            pending_before_item.append(rendered)
                        elif line_base is not None:
                            after_comma_comments.append((priority, rendered))
                        else:
                            pending_before_item.append(rendered)
                    elif parts.prefix in self._single_comment:
                        if line_base is not None:
                            after_comma_comments.append((priority, rendered))
                        else:
                            pending_before_item.append(rendered)
                    else:
                        pending_before_item.append(rendered)
                    continue

                flush_item_line()
                for c in pending_before_item:
                    lines.append(f"{next_ind}{c}")
                pending_before_item = []

                data_seen += 1
                line_base = f"{next_ind}{self.restore(item, depth + 1)}"
                line_has_comma = data_seen < data_total

            flush_item_line()
            for c in pending_before_item:
                lines.append(f"{next_ind}{c}")
            lines.append(f"{ind}]")
            return "\n".join(lines)

        return json.dumps(obj, ensure_ascii=False)

    @cached_property
    def body_restored(self) -> str:
        """按是否后缀seed判断是否为注释，恢复为原来的格式"""
        return self.restore(self.v, 0)

    @property
    def full(self) -> str:
        """header + body + footer"""
        return self.header + self.body_restored + self.footer

    def getitem(
        self,
        key: Iterable[K],
        default=None,
        noRaise: tuple[type[BaseException], ...] = (
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
        ),
    ):
        return get_item(self.v, key, default, noRaise)

    def setitem(self, key: Sequence[K], value, at=UNSET):
        set_item(self if at is UNSET else at, key, value)

    def to_inner_key(self, key: str) -> str:
        """
        translate keyname like("//manual-add") to inner keyname("//manual-add"+SEED) by gen-keyname rule

        or `"//data-key" + AS_DATA` to `"//data-key"`
        """
        if isinstance(key, str) and any(
            (p for p in self._comment_prefixes if key.startswith(p))
        ):
            if key.endswith(AS_DATA):
                return key[: -len(AS_DATA)]
            if not key.endswith(self.SEED):
                return key + self.SEED
        return key

    def __setitem__(self, key: K | Sequence[K] | slice | Any, value):
        if (
            isinstance(key, Sequence)
            and not isinstance(key, (str, bytes, bytearray))
            and isinstance(key[-1], str)
        ):
            key = (*key[:-1], self.to_inner_key(key[-1]))
        elif isinstance(key, str):
            key = self.to_inner_key(key)
        super().__setitem__(key, value)

    def insert_comment(
        self,
        comments: Mapping[K, V],
        key: K | UNSET = UNSET,
        index: int | None = None,
        after=False,
    ):
        """
        内部会判断当前节点是dict还是list类型

        """
        if not comments:
            return

        raw_items = list(comments.items())

        if self.use_ref:
            arr = self.v
            if arr is None:
                raise TypeError("list target is None")
            if not isinstance(arr, list):
                raise TypeError(
                    f"insert_comment() list target must be list, got {type(arr)!r}"
                )
            target_index = len(arr) if index is None else index
            if key is not UNSET and index is None:
                if not isinstance(key, int):
                    raise TypeError(
                        f"list comment key must be int index, got {type(key)!r}"
                    )
                target_index = key + (1 if after else 0)
            target_index = max(0, min(target_index, len(arr)))
            for offset, (k, v) in enumerate(raw_items):
                inner_k = self.to_inner_key(k) if isinstance(k, str) else k
                arr.insert(target_index + offset, {inner_k: v})
            self.del_cache()
            return

        def insert_with_comment_key(
            update: Mapping[Any, Any],
            key: Any | UNSET = UNSET,
            index: int | None = None,
            after=False,
        ):
            if key is UNSET and index is None:
                raise ValueError("key or index must be set")
            if not update:
                return

            keys_before_update = list(self.keys())
            target_index = -1
            if index is not None:
                target_index = index if index >= 0 else len(keys_before_update) + index
                target_index = max(0, min(target_index, len(keys_before_update)))
            elif key is not UNSET:
                lookup_key = self.to_inner_key(key) if isinstance(key, str) else key
                try:
                    target_index = self.index(cast(K, lookup_key))
                    if after:
                        target_index += 1
                except (ValueError, TypeError):
                    raise KeyError(key, "not found")

            inserted_keys: set[Any] = set()
            for k, v in update.items():
                self[k] = v
                actual_k = self.to_inner_key(k) if isinstance(k, str) else k
                self.move_to_end(actual_k)
                inserted_keys.add(actual_k)

            for k in keys_before_update[target_index:]:
                if k not in inserted_keys:
                    self.move_to_end(k)
            self.del_cache()

        line_above_prefixes = tuple(f"{p}\n" for p in self._single_comment)
        single_inline = tuple(self._single_comment)
        before_comments: OrderedDict[Any, Any] = OrderedDict()
        after_comments: OrderedDict[Any, Any] = OrderedDict()
        for k, v in raw_items:
            inner_k = self.to_inner_key(k) if isinstance(k, str) else k
            if (
                isinstance(inner_k, str)
                and inner_k.startswith(single_inline)
                and not inner_k.startswith(line_above_prefixes)
            ):
                after_comments[k] = v
            else:
                before_comments[k] = v

        if index is not None:
            if before_comments:
                insert_with_comment_key(before_comments, index=index, after=False)
            if after_comments:
                insert_with_comment_key(
                    after_comments,
                    index=index + len(before_comments),
                    after=False,
                )
            return
        if key is UNSET:
            tail = len(self)
            if before_comments:
                insert_with_comment_key(before_comments, index=tail, after=False)
                tail += len(before_comments)
            if after_comments:
                insert_with_comment_key(after_comments, index=tail, after=False)
            return
        if before_comments:
            insert_with_comment_key(before_comments, key=key, after=False)
        if after_comments:
            insert_with_comment_key(after_comments, key=key, after=True)

    def comment_out(self, values: Iterable | None = None):
        """
        Usage:
        ```python
        jc[key0, key1].comment_out() # to node comment `/-`
        jc[key0, key1].comment_out([1,2]) # only comment value 1,2 as `/* 1, 2 */`
        ```
        """
        if values is None:
            self.rename_key(new=f"/-{self.keypath[-1][-1]}")
            return
        is_list = iterable(self.v)
        for v in values:
            for k in self.v_to_k(v):
                if is_list:
                    pass  # TODO: value → {"/*counterSEED": value}
                else:
                    self.rename_key(k, "/*counterSEED")

    def del_cache(self):
        super().del_cache()
        del self.body
        try:
            del self.body_restored
        except AttributeError as e:
            pass
            # Log.warning(e)

    def __repr__(self) -> str:
        r = super().__repr__()
        return r if self.repr else r.replace(self.SEED, "")


class hjson[K = str, V = Any](jsonc[K, V]):
    _CommentPrefix = Literal["/*", "//", "#", "/-"]
    _single_comment: tuple[_CommentPrefix, ...] = ("//", "#")


Type_jsonc = jsonc | type[jsonc]


class CompactJSONEncoder(json.JSONEncoder):
    """A JSON Encoder that puts small containers on single lines. by @jannismain at: https://gist.github.com/jannismain/e96666ca4f059c3e5bc28abb711b5c92"""

    CONTAINER_TYPES = (Mapping, Sequence)
    """Container datatypes include primitives or other containers."""

    MAX_WIDTH = 70
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
        if isinstance(o, Mapping):
            return self._encode_object(o)
        if iterable(o):
            return self._encode_list(o)
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

    def iterencode(self, o, **kwargs):
        """Required to also work with `json.dump`."""
        return self.encode(o)

    def _put_on_single_line(self, o):
        return (
            self._primitives_only(o)
            and len(o) <= self.MAX_ITEMS
            and len(str(o)) - 2 <= self.MAX_WIDTH
        )

    def _primitives_only(self, o: list | tuple | dict):
        if isinstance(o, Mapping):
            return not any(isinstance(el, self.CONTAINER_TYPES) for el in o.values())
        if iterable(o):
            return not any(isinstance(el, self.CONTAINER_TYPES) for el in o)

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
