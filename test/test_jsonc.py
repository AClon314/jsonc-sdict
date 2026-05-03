import json
import logging
from pathlib import Path

import hjson
import pytest

from jsonc_sdict import NONE, UNSET
from jsonc_sdict.jsonc import Within, hjsonDict, is_comment, jsoncDict

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
    assert jd.comments[Within(NONE, "0")] == '// {\n  // "": null,'
    assert jd.comments[Within("6//")] == "/* 6 */"
    assert Within(0, 1) not in jd.comments
    assert isinstance(ls, jsoncDict)
    assert ls.comments[Within(0, 1)] == "// 1,"


def test_comments_collects_nested_comment_maps():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    comments = jd.comments_flat

    assert () in comments
    assert ("list",) in comments
    assert comments.get(())[Within("6//")] == "/* 6 */"
    assert comments.get(("list",))[Within(0, 1)] == "// 1,"


def test_jsoncdict_preserves_current_depth_order():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    items = list(jd.items())

    assert items[0] == (Within(NONE, "0"), '// {\n  // "": null,')
    assert items[1] == ("0", 0)
    assert items[2] == (Within("0", "2"), '// 0\n  // "1": 1, /* 1 */')
    assert items[3] == ("2", 2)
    assert is_comment(items[0][0])
    assert not is_comment(items[1][0])
    assert jd.mixed[Within("6//")] == "/* 6 */"


@pytest.mark.xfail(
    strict=True,
    raises=KeyError,
    reason="array child mixed-view iteration is currently broken for list-backed nodes",
)
def test_jsoncdict_recurses_into_nested_jsoncdict():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    mixed_list = jd.mixed["list"]

    assert isinstance(mixed_list, jsoncDict)
    assert mixed_list[0] == 0
    assert mixed_list[Within(0, 1)] == "// 1,"
    assert mixed_list[1] == "2"


def test_hidden_key_uses_comments_runtime_marker():
    jd = jsoncDict({"keep": 1, "hide": 2, "tail": 3})
    jd.comments["hide"] = ""

    assert list(jd.items()) == [("keep", 1), ("tail", 3)]
    assert list(jd) == ["keep", "tail"]
    assert len(jd) == 2
    with pytest.raises(KeyError):
        jd["hide"]


def test_mixed_only_skips_hidden_keys_on_that_child_depth():
    jc = jsoncDict(
        {
            "node": {"keep": 1, "hide": 2},
            "tail": 3,
        }
    )

    node = jc["node"]
    node.comments["hide"] = ""

    assert list(jc.mixed.keys()) == ["node", "tail"]
    assert list(node.mixed.keys()) == ["keep"]


def test_init_splits_top_level_mixed_mapping():
    jd = jsoncDict({Within(NONE, "a"): "// a", "a": 1})

    assert jd.data["a"] == 1
    assert jd.comments[Within(NONE, "a")] == "// a"
    assert list(jd.items()) == [(Within(NONE, "a"), "// a"), ("a", 1)]


def test_init_splits_kv_slot_comment_mapping():
    jd = jsoncDict({"a": {Within("k", ":"): "/*c*/"}})

    assert "a" not in jd.data
    assert jd.comments["a"] == {Within("k", ":"): "/*c*/"}


def test_init_auto_splits_nested_mixed_mapping():
    jd = jsoncDict({"node": {"x": 1, Within("x"): "/*c*/"}})

    node = jd["node"]
    assert isinstance(node, jsoncDict)
    assert node.data["x"] == 1
    assert node.comments[Within("x")] == "/*c*/"
    assert list(node.items()) == [("x", 1), (Within("x"), "/*c*/")]


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
    assert jd._dumps_add_indent("x\ny", "  ") == "x\ny"


def test_children_resync_after_data_key_rename():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)
    child = jd.mixed["list"]

    jd.data.rename_key("list", "items")

    assert jd.mixed["items"] is child
    assert child.comments[(0, 1)] == "// 1,"


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason="jsonc.dumps/body restore path is still unfinished",
)
def test_jsonc_body_restore_is_not_ready():
    jc = make_jsonc({"a": 1})
    assert '"a": 1' in jc.body
