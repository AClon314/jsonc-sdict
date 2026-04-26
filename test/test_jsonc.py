import json
import logging
from collections import OrderedDict
from pathlib import Path

import hjson
import pytest

from jsonc_sdict import UNSET
from jsonc_sdict.Sdict import sdict
from jsonc_sdict.jsonc import Between, hjsonDict, is_comment, jsoncDict

Log = logging.getLogger()


def json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def make_jsonc(raw, **kwargs):
    kwargs.setdefault("deep", False)
    return jsoncDict(raw, hjson.loads, dumps=json_dumps, **kwargs)


def make_hjson(raw, **kwargs):
    kwargs.setdefault("deep", False)
    return hjsonDict(raw, hjson.loads, dumps=json_dumps, **kwargs)


def test_init():
    In = Path("test/old.jsonc")
    jd = jsoncDict(In.read_text("utf-8"), loads=hjson.loads, dumps=json_dumps)
    Log.debug(f"{jd._comments=}")
    Log.debug(f"{jd.comments=}")
    Log.debug(f"{jd.mixed=}")
    assert jd._comments


def test_loads_collects_header_footer_and_comments():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)
    ls = jd["list"]

    assert jd.header.startswith("/** aclon314 {} */")
    assert jd.footer == "\n// eof"
    assert jd._comments[(UNSET, "0")] == '// {\n  // "": null,'
    assert jd._comments[("6//", "6//")] == "/* 6 */"
    assert (0, 1) not in jd._comments
    assert isinstance(ls, jsoncDict)
    assert ls._comments[(0, 1)] == "// 1,"


def test_comments_collects_nested_comment_maps():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    comments = jd.comments

    assert () in comments
    assert ("list",) in comments
    assert comments.get(())[("6//", "6//")] == "/* 6 */"
    assert comments.get(("list",))[(0, 1)] == "// 1,"


def test_mixed_preserves_current_depth_order():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    mixed = jd.mixed
    items = list(OrderedDict.items(mixed))

    assert items[0] == (Between(UNSET, "0"), '// {\n  // "": null,')
    assert items[1] == ("0", 0)
    assert items[2] == (Between("0", "2"), '// 0\n  // "1": 1, /* 1 */')
    assert items[3] == ("2", 2)
    assert is_comment(items[0][0])
    assert not is_comment(items[1][0])
    assert mixed[Between("6//", "6//")] == "/* 6 */"


def test_mixed_recurses_into_nested_jsoncdict():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    mixed_list = jd.mixed["list"]

    assert isinstance(mixed_list, sdict)
    assert mixed_list[0] == 0
    assert mixed_list[Between(0, 1)] == "// 1,"
    assert mixed_list[1] == "2"


@pytest.mark.xfail(
    strict=True,
    raises=NameError,
    reason="jsonc.dumps/body restore path is still unfinished",
)
def test_jsonc_body_restore_is_not_ready():
    jc = make_jsonc({"a": 1})
    assert '"a": 1' in jc.body
