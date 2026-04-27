import json
import logging
from pathlib import Path

import hjson
import pytest

from jsonc_sdict import UNSET
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
    Log.debug(f"{jd.comments=}")
    Log.debug(f"{jd.comments_flat=}")
    Log.debug(f"{jd.mixed=}")
    Log.debug(f"{jd.children=}")
    assert jd.comments


def test_loads_collects_header_footer_and_comments():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)
    ls = jd["list"]

    assert jd.header.startswith("/** aclon314 {} */")
    assert jd.footer == "\n// eof"
    assert jd.comments[(UNSET, "0")] == '// {\n  // "": null,'
    assert jd.comments[("6//", "6//")] == "/* 6 */"
    assert (0, 1) not in jd.comments
    assert isinstance(ls, jsoncDict)
    assert ls.comments[(0, 1)] == "// 1,"


def test_comments_collects_nested_comment_maps():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    comments = jd.comments_flat

    assert () in comments
    assert ("list",) in comments
    assert comments.get(())[("6//", "6//")] == "/* 6 */"
    assert comments.get(("list",))[(0, 1)] == "// 1,"


def test_jsoncdict_preserves_current_depth_order():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    items = list(jd.mixed.items())

    assert items[0] == (Between(UNSET, "0"), '// {\n  // "": null,')
    assert items[1] == ("0", 0)
    assert items[2] == (Between("0", "2"), '// 0\n  // "1": 1, /* 1 */')
    assert items[3] == ("2", 2)
    assert is_comment(items[0][0])
    assert not is_comment(items[1][0])
    assert jd.mixed[Between("6//", "6//")] == "/* 6 */"


def test_jsoncdict_recurses_into_nested_jsoncdict():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    mixed_list = jd.mixed["list"]

    assert isinstance(mixed_list, jsoncDict)
    assert mixed_list[0] == 0
    assert mixed_list[Between(0, 1)] == "// 1,"
    assert mixed_list[1] == "2"


def test_jsoncdict_missing_class_loads_raises_value_error():
    class NoLoads(jsoncDict):
        pass

    NoLoads.config(loads=None)
    with pytest.raises(ValueError, match="missing arg `loads`"):
        NoLoads("{}")


def test_subclass_class_config_is_not_reset_by_init_defaults():
    class NoIndent(jsoncDict):
        auto_indent = False

    NoIndent.config(loads=hjson.loads)
    jd = NoIndent('{"a": 1}')

    assert type(jd).auto_indent is False
    assert jd._add_indent("x\ny", "  ") == "x\ny"


def test_children_resync_after_data_key_rename():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)
    child = jd.mixed["list"]

    jd.data.rename_key("list", "items")

    assert jd.mixed["items"] is child
    assert child.comments[(0, 1)] == "// 1,"


@pytest.mark.xfail(
    strict=True,
    raises=NameError,
    reason="jsonc.dumps/body restore path is still unfinished",
)
def test_jsonc_body_restore_is_not_ready():
    jc = make_jsonc({"a": 1})
    assert '"a": 1' in jc.body
