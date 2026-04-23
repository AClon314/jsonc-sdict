#!/bin/env python3
"""
comment-keyname rules:

| Internal key prefix | Means | Restored shape |
| --- | --- | --- |
| `//` | single-line comment, inline mode | **after** current value/comma, stay in line with value |
| `//\\n` | single-line comment, line-above mode | independent line before next key/value |
| `/* ` | block comment (default) | **after** comma`,`, stay in line with value |
| `/*\\n` | block comment, line-above mode | independent line before next key/value |
| `/*,` | block comment before comma | placed before comma of current item |
| `/*k` | block comment before key slot | before JSON key token |
| `/*:` | block comment before colon slot | between key and value |
| `/*v` | block comment before value slot | after colon, before value |
| `/-` | slash_dash comment | comments out a whole subtree (KDL-like style) |
```
"""

import re
import json
from dataclasses import dataclass
from collections.abc import (
    Callable,
    Generator,
    Mapping,
    Sequence,
    Iterable,
    MutableSequence,
)
from typing import Any, Unpack, Literal, cast, Self
from warnings import deprecated

from jsonc_sdict.share import (
    UNSET,
    RegexPattern,
    Scalar,
    getLogger,
    iterable,
    isFlatIterable,
    args_of_type,
    copy_args,
    _TODO,
    search,
)
from jsonc_sdict.Sdict import sdict, set_item, get_item, unref

Log = getLogger(__name__)
_Type_BeforeSep = Literal["", "\n", ",", "k", ":", "v"]
"""k : v , \n"""
before_seps = args_of_type(_Type_BeforeSep)
_Type_DataOrComment = Literal["data", "comment"]


def _esc_for_regex(unEsc: str) -> str:
    return re.escape(unEsc).replace('"', '\\"')


@dataclass
class CommentData:
    prefix: "hjsonDict._CommentPrefix"
    name: str
    before: _Type_BeforeSep = ""

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
    _comment_prefixes: tuple[_Type_CommentPrefix, ...] = args_of_type(
        _Type_CommentPrefix
    )  # type: ignore
    _comment_single: tuple[_Type_CommentPrefix, ...] = ("//",)
    """must be ordered longest to shortest for find()"""
    _comment_multi: dict[_Type_CommentPrefix, str] = {"/*": "*/"}
    """{tag_start: tag_end}"""
    _dumps_raw = json_dumps
    slash_dash = True
    """default True. if key_name starts_with `/-`, like `/-mynode` will comment the whole tree node, see [kdl](https://kdl.dev/) config style"""
    auto_indent = True
    """default True, auto-indent for multi-line comment. if False, then you need manually handle indent"""
    merge_single = True
    """
    `{"//":" comment1\\n comment2"}` if True else `{"//1": " comment1", "//2": " comment2"}`
    ```
    // comment1
    // comment2
    ```
    """
    header = ""
    footer = ""
    forceDataKeys: set[RegexPattern | tuple[str, ...]] = set()
    """tuple[str,...] will match keypath, while str will match the current node's key"""
    _pos = 0
    """loads()/scan() temp pointer"""

    def __init_subclass__(cls) -> None:
        cls._comment_prefixes = args_of_type(cls._Type_CommentPrefix)  # type: ignore
        # TODO: sort _comment_single, longest at first

    def __init__(
        self,
        data: str | Mapping[K, V],
        loads: Callable[[str], Any] | None = None,
        dumps: Callable[[Any], str] = _dumps_raw,
        slash_dash: bool = slash_dash,
        auto_indent: bool = auto_indent,
        has_comment: bool = True,
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
            has_comment:
                None: default, auto choose True if isinstance(data, str) else False. This is for `jsoncDict(myDict)`
                False: treat **all comment_prefix keys as data key, not comment** key, by **recorded in `self.forceDataKeys`**. Or you promise there's no comment key.
                True: if key name satisfy the comment-keyname rule, do nothing internally.
            **kwargs: see `sdict()`
        """
        self._loads_raw = loads
        self._dumps_raw = dumps
        self.slash_dash = slash_dash
        self.auto_indent = auto_indent

        if not slash_dash:
            styles = list(self._comment_prefixes)
            styles.remove("/-")
            self._comment_prefixes = tuple(styles)

        if isinstance(data, str):
            if self._loads_raw is None:
                raise ValueError("missing arg `loads` when `raw` is str")
            if has_comment is None:
                has_comment = True
            obj = self.loads_raw(data)
            # data(dict): have un-converted comments, miss raw's comments
            # raw(str): have comments & data raw info
        else:
            if has_comment is None:
                has_comment = True
            obj = data
            data = ""
            # data(dict): have un-converted comments
            # raw(str): empty
        # NOTE: 其实raw(str)并不重要，我们只关心 data(dict)
        # `sdict.__init__` may call `self.__setitem__`, so setup attrs before this call.
        super().__init__(obj, **kwargs)
        self.loads(data, has_comment=has_comment)

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

    def split_key(self, key: str | Any = UNSET) -> CommentData | None:
        """
        return CommentData if is comment, else None

        Args:
            key: if UNSET, fallback to itself keypath(`self.keypath[-1]`)
        """
        if key is UNSET:
            key = self.keypath[-1]
        if not (isinstance(key, str)):
            return
        for prefix in self._comment_prefixes:
            if key.startswith(prefix):
                sep = cast(_Type_BeforeSep, key[len(prefix)])
                # single-comment only 2 modes: `//` and `//\n` (or `#` and `#\n`)
                reset_single = prefix in self._comment_single and sep != "\n"
                if reset_single or sep not in before_seps or prefix == "/-":
                    sep = ""
                return CommentData(prefix=prefix, before=sep, name=key[len(prefix) :])

    @deprecated("also you can use `split_key()`")
    @copy_args(split_key)
    def is_comment(self, *args, **kw) -> CommentData | None:
        return self.split_key(*args, **kw)

    def _match_comment_single_prefix(self, text: str, idx: int) -> str | None:
        for prefix in self._comment_single:
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
        if any(prefix.startswith(single) for single in self._comment_single):
            val = val.rstrip("\n")
        val = self._add_indent(val, indent)

        if prefix.startswith("/*"):
            return f"/*{val}*/"
        for single in self._comment_single:
            if prefix.startswith(single):
                return f"{single}{val}"
        return f"{prefix}{val}"

    def _new_CommentKey(
        self, prefix: _Type_CommentPrefix, name: str | Any
    ) -> CommentData:
        # TODO: 重写为 //myKey, myKey。上方注释key跟随下方datakey。重名时后缀加数字
        # TODO: t"" template string in python 3.15
        return CommentData(prefix=prefix, name=name)

    def _scan(
        self,
        raw: str,
        initSend: RegexPattern,
        initPos: int = 0,
    ) -> Generator[
        list[tuple[_Type_CommentPrefix, str]],
        RegexPattern,
        list[tuple[_Type_CommentPrefix, str]],
    ]:
        """must .send(next_data_key), and will yield comments above this data key."""
        PATTERN = cast(re.Pattern, initSend)
        Match = PATTERN.match(raw, pos=initPos)
        if Match is None:
            raise ValueError(
                f"Not found the first pattern in raw, check your `{initSend=}` or `{initPos=}`",
                locals(),
            )
        TypePrefix = jsoncDict._Type_CommentPrefix
        self._pos = initPos
        multi_vk: dict[str, TypePrefix] = {v: k for k, v in self._comment_multi.items()}
        multi_starts: dict[TypePrefix, int] = {}
        single_starts: dict[TypePrefix, int] = {}
        max_len = max((len(p) for p in self._comment_prefixes), default=1) + 1
        Log.debug(
            "self._comment_prefixes=%s\tmax_len=%s", self._comment_prefixes, max_len
        )
        COMMENTS: list[tuple[TypePrefix, str]] = []
        START = 0
        # NOTE: 加入Match的属于注释区，则仍然需要向后搜索，直到不再是注释区且命中token
        while self._pos < Match.pos:
            step = 1
            # NOTE: chars could be ["a","ab","abc"...], so chars[len(prefixes)-1]
            chars = [raw[self._pos : self._pos + size] for size in range(1, max_len)]
            set_chars = set(chars)
            if chars[0] == "\n" and single_starts:
                # // end
                prefix, single_start_pos = single_starts.popitem()
                text = raw[single_start_pos + len(prefix) : self._pos]
                PATTERN = yield prefix, text
                single_starts = {}
            elif not single_starts and (
                single_prefixes := set_chars.intersection(self._comment_single)
            ):
                # // start
                single_prefix = cast(TypePrefix, single_prefixes.pop())
                single_starts = {single_prefix: self._pos}
                step = len(single_prefix)
            elif multi_prefixes := set_chars.intersection(self._comment_multi):
                # /*
                len_ms = len(multi_prefixes)
                if len_ms > 1:
                    Log.warning(
                        "Unexpected len(multi_starts)=%s > 1, fallback multi_starts.pop()",
                        len_ms,
                    )
                prefix = cast(TypePrefix, multi_prefixes.pop())
                multi_starts[prefix] = self._pos
                step = len(prefix)
            elif multi_ends := set_chars.intersection(multi_vk):
                # */
                len_me = len(multi_ends)
                if len_me > 1:
                    Log.warning(
                        "Unexpected len(multi_ends)=%s > 1, fallback multi_ends.pop()",
                        len_me,
                    )
                multi_end = multi_ends.pop()
                multi_prefix = multi_vk[multi_end]
                if next(reversed(multi_starts)) == multi_prefix:
                    _, start = multi_starts.popitem()
                    step = len(multi_end)
                    text = raw[start + len(multi_prefix) : self._pos]
                    PATTERN = yield multi_prefix, text
                else:
                    raise ValueError(
                        f"Invalid closing symbol for current {chars[-1]=}, {multi_prefix=} should be the last one in {multi_starts=}"
                    )
            assert PATTERN is not None, "Must .send(PATTERN) to continue yield!"
            Log.debug("chars=%s\tpos=%s\tstep=%s", chars, self._pos, step)

            # NOTE: 如果注释没闭合，则往后搜索
            if single_starts or multi_starts:
                Match = PATTERN.match(raw, pos=Match.pos)
                if Match is None:
                    raise ValueError(
                        f"Invalid closing symbol for current {chars[-1]=} while not found the next data key as {PATTERN=}, {single_starts=} & {multi_starts=}"
                    )
            else:
                PATTERN = yield COMMENTS[START:]
                START = len(COMMENTS)
            self._pos += step
        return COMMENTS

    @staticmethod
    def _regex_key(key: str, flags: re._FlagsType = re.DOTALL) -> re.Pattern[str]:
        """locate the next data key"""
        # toml= yaml: json"":
        return re.compile(f'"{_esc_for_regex(key)}"(.*):', flags=flags)

    @staticmethod
    def _regex_value(
        value: Scalar, flags: re._FlagsType = re.DOTALL, isLast: bool = False
    ) -> re.Pattern[str]:
        """locate the next data value of dict&list. `[/*comment*/0,1,2]` or `: value, ...`"""
        assert value is None or isinstance(value, (bool, int, float, str)), _TODO
        if isinstance(value, str):
            esc = f"{_esc_for_regex(value)}"
        elif isinstance(value, bool):
            esc = "true" if value else "false"
        elif value is None:
            esc = "null"
        else:
            esc = re.escape(str(value))
        if not isLast:
            esc += "(.*),"
        return re.compile(esc, flags=flags)

    def loads(self, raw: str = "", has_comment: bool = False) -> Mapping:
        """bake `self` data-only-dict with hint from `raw` (like `self`'s crutch🦯)"""
        # toml,  yaml,\n  json,
        if has_comment and not raw:
            return self
        raw = raw.replace("\r", "")

        # TODO: 搜索 token
        gen_items = self.items_flat(withParents=True, readonly=False)
        # NOTE: find header
        # NOTE: .send(None)所以需要单独处理
        keypath, value = next(gen_items)
        key = keypath[-1]
        if isinstance(value, sdict):
            value = value.v
        if iterable(value):
            value = "{" if isinstance(value, Mapping) else "["
        PATTERN = (
            self._regex_key(key)
            if isinstance(self.v, Mapping)
            else self._regex_value(value)
        )
        gen_scan = self._scan(raw, initSend=PATTERN)
        # key mode in dict + value mode in list(last one without `,`)

        for idx, (keypath, nodeOrV) in enumerate(gen_items):
            key: str = keypath[-1]
            while _comments := gen_scan.send(self._regex_key()):
                prefix, text = _comments
                Log.debug(f"{prefix=}\t{text=}")

            comment = self.split_key(key)
            Log.debug("key=%s\tcomment=%s", key, comment)
            if not comment:
                continue
            else:  # iterable
                pass
        # NOTE:has_comment 为 false 时，需要额外记录 forceDataKeys
        # NOTE: find footer

        return body

    def dumps(self, obj: Any | None = None, depth=0) -> str:
        """restore"""
        if obj is None:
            obj = self.v
        obj = unref(obj)
        inner = self.dumps_raw(obj)
        # TODO: implement this

        return out

    def data(self) -> Self:
        """data only, no comment"""
        # TODO: implement this
        view = type(self)(self)
        return view

    def comments(self) -> Self:
        """comments only, no data"""
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
        | `/* ` | block comment (default) | **after** comma`,`, stay in line with value |
        | `/*\\n` | block comment, line-above mode | independent line before next key/value |
        | `/*,` | block comment before comma | placed before comma of current item |
        | `/*k` | block comment before key slot | before JSON key token |
        | `/*:` | block comment before colon slot | between key and value |
        | `/*v` | block comment before value slot | after colon, before value |
        | `/-` | slash_dash comment | comments out a whole subtree (KDL-like style) |
        """
        # TODO: adjust to latest rule
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

    def switch(
        self,
        From: _Type_DataOrComment | None = None,
        to: _Type_DataOrComment | Literal["invert"] = "comment",
        children: Iterable | None = None,
        unpack: bool = True,
    ):
        """
        Args:
            From: filter
            to: "invert" means toggle
            children: current node's children item
            unpack: wheter remove prefix(`/-` or `//`...), or extract value from temporary commentDict if switch to comment.

        Usage:
        ```python
        jc[key0, key1].switch() # to slash_dash comment `/-`

        # jc[key0,key1] = [0,1,2,3]
        jc[key0, key1].switch([1,2]) # only comment out `1,2` to `/* 1, 2 */`
        # assert jc[key0,key1] == [0,{"//\\n1":1},{"//\\n2":2},3]
        ```
        """
        # TODO: implement this in the future
        if children is None:
            wasComment = self.is_comment()
            if to == "invert":
                to = "data" if wasComment else "comment"
            if wasComment and to == "data":
                parent = self.parent
                # 去掉prefix与before，只保留name
                if unpack and parent is not None:
                    # TODO: 应该规定parent只能为sdict类型
                    isParentMap = (
                        isinstance(parent, sdict)
                        and isinstance(parent.v, Mapping)
                        or isinstance(parent, Mapping)
                    )
                    if isParentMap:
                        wasComment.prefix = ""
                        wasComment.before = ""
                        self.rename_key(new=str(wasComment))
                    else:
                        parent = cast(MutableSequence, parent)

                self.forceDataKeys.add(str(wasComment))
            elif not wasComment and to == "comment":
                if self.slash_dash:
                    prefix = "/-"
                else:
                    prefix = "//\n"
                self.rename_key(new=f"{prefix}{self.keypath[-1]}")
                if str(wasComment) in self.forceDataKeys:
                    self.forceDataKeys.remove(str(wasComment))
            return

        isContainer = iterable(self.v)
        for v in children:
            for k in self.v_to_k(v):  # TODO
                if isContainer:
                    pass  # TODO: value → {"/*counterSEED": value}
                else:
                    self.rename_key(k, "/*counterSEED")


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
