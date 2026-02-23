#!/bin/env python3
""""""
import os
import json
import typing
import logging
from collections import UserDict
from collections.abc import Callable
from deepdiff import DeepDiff

P = typing.ParamSpec("P")
LOG = os.environ.get("LOG", "INFO").upper()
IS_DEBUG = LOG == "DEBUG" or os.environ.get("TERM_PROGRAM", None)
logging.basicConfig(format="%(levelname)s %(asctime)s %(name)s:%(lineno)d\t%(message)s")
Log = logging.getLogger(__name__)
Log.setLevel(logging.DEBUG if IS_DEBUG else LOG)


class jsonc_sdict(UserDict):
    """
    pre-processor & dict-wrapper (calc)

    inherite this class for your custom config format(toml/yaml...)
    """

    data: dict
    """raw data"""
    comments: dict[tuple, str]
    """only comments"""

    Seperator = typing.Literal["\n", '"', ":", ","]
    seps: tuple[Seperator] = typing.get_args(Seperator)
    CommentMode = typing.Literal["//\n", "//_", "/*/"]
    commentModes: tuple[CommentMode] = typing.get_args(CommentMode)

    def __init_subclass__(cls) -> None:
        cls.seps = typing.get_args(cls.Seperator)
        cls.commentModes = typing.get_args(cls.CommentMode)
        assert (
            len(set(len(s) for s in cls.commentModes)) == 1
        ), f"need fixed-width {cls.commentModes=}"

    def __init__(self, text: str, dict):
        self._text = text
        self._body, self._header, self._footer = comment_alive(
            self=self, text=self._text
        )

    def gen_keyName(
        self,
        groupDict: dict[str, str | None],
        count: int,
        digit: int,
        **kwargs: dict[str, typing.Any],
    ):
        return gen_keyName(groupDict=groupDict, count=count, digit=digit)

    def comment_split(self, keyName: str):
        return comment_split(keyName=keyName)

    @property
    def text(self):
        return self._text

    @property
    def body(self):
        return self._body

    @property
    def header(self):
        return self._header

    @property
    def footer(self):
        return self._footer


Type_jsonc_sdict = jsonc_sdict | type[jsonc_sdict]


def find_bodyEdge(text: str):
    """
    Find the starting and ending index of the first valid jsonc body {}
    找到第1个有效 jsonc body {} 的起止索引
    """
    in_multi = False  # 在多行注释 /* */ 中
    in_single = False  # 在单行注释 // 中
    body_start = None
    idx = 0

    while idx < len(text):
        c = text[idx]  # 简化当前字符变量名

        # 1. 跳过单行注释（直到换行）
        if in_single:
            if c == "\n":
                in_single = False
            idx += 1
            continue

        # 2. 跳过多行注释（直到 */）
        if in_multi:
            if c == "*" and idx + 1 < len(text) and text[idx + 1] == "/":
                in_multi = False
                idx += 2
            else:
                idx += 1
            continue

        # 3. 检测注释开始（合并判断，减少冗余）
        if c == "/" and idx + 1 < len(text):
            if text[idx + 1] == "*":
                in_multi = True
                idx += 2
                continue
            elif text[idx + 1] == "/":
                in_single = True
                idx += 2
                continue

        # 4. 定位非注释区的 {}
        if body_start is None and c == "{":
            body_start = idx
        elif body_start is not None and c == "}":
            return (body_start, idx + 1)  # 找到后直接返回，省去body_end变量

        idx += 1

    raise ValueError("bodyEdge NOT found, json must have {{ }} bracket as root")


def gen_keyName(
    groupDict: dict[str, str | None], count: int, digit: int
) -> tuple[jsonc_sdict.CommentMode, str, str]:
    """gen a unique key name to tell that is not data, but the comment string.

    gen rule(生成规则):
    - //_0001    comment modumpsde(in same line) + count
    - /*/0002":  comment mode(multi lines) + count + previous char(") + after char(:)

    //\\n comment above line 行上注释

    //_ comment in same line 行内注释

    /*/ 多行注释+前一个符号+后一个符号(`_v` `_"` `":` `:v` `v,` `,_`)

    Returns:
        mode (jsonc_sdict.CommentMode): ...
        counter (str): space ` ` as left-padding
        suffix: multi-lines needs extra data to keep original format
    """
    single = groupDict["single"]
    multi = groupDict["multi"]
    suffix = ""
    if single is not None:
        before = groupDict["s_before"]
        mode = "//_" if before else "/*/"
    elif multi is not None:
        before = groupDict["m_before"]
        after = groupDict["m_after"]
        mode = "/*/"
        if before and (before := before.strip()):
            suffix += before[-1]
        else:
            suffix += "\n"
        if after and (after := after.strip()):
            suffix += after[0]
        else:
            suffix += "\n"
    else:
        raise ValueError(f"{single=} and {multi=}, you shouldn't invoke this function!")

    counter = f"{count:{digit}d}"
    return mode, counter, suffix


def comment_split(keyName: str):
    """
    Also can judge if the keyName is from comment or data.

    Returns:
        mode (jsonc_sdict.CommentMode):

        counter (str): of comments

        ab (str): prefix(before) + suffix(after) char

    """
    mode = typing.cast(jsonc_sdict.CommentMode, keyName[:3])
    if mode == "/*/":
        if len(keyName) > 3:
            counter = keyName[3:-2]
            ab = keyName[-2:]
        else:
            counter = ab = ""
    elif mode in ("//_", "//\n"):
        counter = keyName[3:]
        ab = None
    else:
        return None, None, None
    return mode, counter, ab


def comment_alive(text: str, self: Type_jsonc_sdict = jsonc_sdict):
    """
    insert comments to data, ready for `jsonXXX.loads()`

    Args:
        text: the text content of jsonc/json5
        self: config class
    Returns:
        body: {"existed data": "...", "//_ 1": " \\\\"escaped\\\\" comment", "/*/ 2": "comment\\nlines"}

        header: before body

        footer: after body

        *'``・* 。\n
    　  |　　    `*。  復活して下さい、愛しい人よ~\n
    　,｡∩　　　 *\n
    +　(´• ω•`)　*｡+ﾟ\n
    `*｡ ヽ、　 つ *ﾟ*    // 💀: who? me?\n
    　`・+｡*・' ﾟ⊃ +ﾟ\n
    　☆　　 ∪~ ｡*ﾟ\n
    　　`・+｡*・ ﾟ
    """
    start, end = find_bodyEdge(text)
    body = text[start:end].replace("\r", "")

    _comments: list[str] = self.pattern.findall(text)
    digit = len(str(len(_comments)))

    count = 0
    iters = self.pattern.finditer(body)
    for match in iters:
        g = match.groupdict()
        elements = gen_keyName(groupDict=g, count=count, digit=digit)
        keyName = "".join(elements)
        A, B = match.span()
        old = body[A:B].replace("\\", "\\\\").replace('"', r"\"")  # TODO: test
        new = f'"{keyName}": "{old}",'
        # TODO: 若在list[]内，外层需加个{}

        if elements[0] == "/*/":
            # 找到上一行
            idx = A - 1
            while text[idx] != "\n" or idx > start + 1:  # TODO: test
                idx -= 1
            body = body[:idx] + new + body[idx:A] + body[B:]
        else:
            body = body[:A] + new + body[B:]
        Log.debug(f"{old}\n{new}")
        count += 1
    return body, text[:start], text[end:]


def dumps(
    diff: DeepDiff,
    dumps: Callable[[typing.Any], str] = json.dumps,
    **dumps_kwargs,
):
    return ""


class CompactJSONEncoder(json.JSONEncoder):
    """A JSON Encoder that puts small containers on single lines. by @jannismain at: https://gist.github.com/jannismain/e96666ca4f059c3e5bc28abb711b5c92"""

    CONTAINER_TYPES = (list, tuple, dict)
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


def test():
    from pprint import pprint
    import ujson5

    with open("test/old.jsonc", "r") as f:
        text = f.read()
    pprint(comment_alive(text))
    data = ujson5.loads(text)
    with open("test/new.jsonc", "w") as f:
        f.write(ujson5.dumps(data, indent=2))


if __name__ == "__main__":
    test()
