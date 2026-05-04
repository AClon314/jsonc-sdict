import json
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Any

import hjson
import pytest

from jsonc_sdict import NONE, UNSET
from jsonc_sdict.share import _TODO
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
    jd = jsoncDict(
        In.read_text("utf-8"), loads=hjson.loads, dumps=json_dumps, slash_dash=False
    )
    Log.debug(f"{jd.comments=}")
    Log.debug(f"{jd.comments_flat=}")
    Log.debug(f"{jd.mixed=}")
    Log.debug(f"{jd.children=}")
    assert jd.comments


def test_loads_collects_header_footer_and_comments():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps, slash_dash=False)
    ls = jd["list"]

    assert jd.header.startswith("/** aclon314 {} */")
    assert jd.footer == "\n// eof"
    assert jd.comments[Within(NONE, "0")] == '// {\n  // "": null,'
    assert jd.comments[Within("6//")] == {Within(":", "v"): "/* 6 */"}
    assert Within(0, 1) not in jd.comments
    assert isinstance(ls, jsoncDict)
    assert ls.comments[Within(0, 1)] == "// 1,"


def test_comments_collects_nested_comment_maps():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps, slash_dash=False)

    comments = jd.comments_flat

    assert () in comments
    assert ("list",) in comments
    assert comments.get(())[Within("6//")] == {Within(":", "v"): "/* 6 */"}
    assert comments.get(("list",))[Within(0, 1)] == "// 1,"


def test_jsoncdict_preserves_current_depth_order():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps, slash_dash=False)

    items = list(jd.items())

    assert items[0] == (Within(NONE, "0"), '// {\n  // "": null,')
    assert items[1] == ("0", 0)
    assert items[2] == (Within("0", "2"), '// 0\n  // "1": 1, /* 1 */')
    assert items[3] == ("2", 2)
    assert is_comment(items[0][0])
    assert not is_comment(items[1][0])
    assert jd.mixed()[Within("6//")] == {Within(":", "v"): "/* 6 */"}


def test_jsoncdict_recurses_into_nested_jsoncdict():
    raw = Path("test/old.jsonc").read_text("utf-8")
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps, slash_dash=False)

    mixed_list = jd.mixed()["list"]

    assert isinstance(mixed_list, jsoncDict)
    assert mixed_list[0] == 0
    assert mixed_list[Within(0, 1)] == "// 1,"
    assert mixed_list[1] == "2"


def test_hidden_key_uses_comments_runtime_marker():
    jd = jsoncDict({"keep": 1, "hide": 2, "tail": 3})
    jd.comments["hide"] = {"reason": "runtime hidden"}

    assert list(jd.items()) == [("keep", 1), ("tail", 3)]
    assert list(jd.items(comments=False)) == [("keep", 1), ("tail", 3)]
    assert list(jd) == ["keep", "tail"]
    assert len(jd) == 2
    with pytest.raises(KeyError):
        jd["hide"]


def test_len_matches_materialized_items_for_visible_mixed_view():
    jd = jsoncDict({Within(None, "a"): "// dangling", "a": 1, Within("a"): "/*c*/"})

    assert list(jd.items()) == [("a", 1), (Within("a"), "/*c*/")]
    assert list(jd.items(comments=False)) == [("a", 1)]
    assert len(jd) == len(list(jd.items()))


def test_repr_uses_visible_mixed_view():
    jd = jsoncDict({Within(NONE, "a"): "// head", "a": 1, Within("a"): "/*c*/"})

    assert repr(jsoncDict({})) == "jsoncDict()"
    assert repr(jd) == "jsoncDict({Within(NONE, 'a'): '// head', 'a': 1, Within('a',): '/*c*/'})"


def test_within_only_equals_within():
    assert Within("a", "b") == Within("a", "b")
    assert Within("a") == Within("a")
    assert Within("a", "b") != ("a", "b")
    assert Within("a") != ("a",)
    assert hash(Within("a", "b")) == hash(Within("a", "b"))


def test_mixed_only_skips_hidden_keys_on_that_child_depth():
    jc = jsoncDict(
        {
            "node": {"keep": 1, "hide": 2},
            "tail": 3,
        }
    )

    node = jc["node"]
    node.comments["hide"] = {"reason": "runtime hidden"}

    assert list(jc.mixed().keys()) == ["node", "tail"]
    assert list(jc.mixed(comments=False).keys()) == ["node", "tail"]
    assert list(node.mixed().keys()) == ["keep"]
    assert list(node.mixed(comments=False).keys()) == ["keep"]


def test_init_splits_top_level_mixed_mapping():
    jd = jsoncDict({Within(NONE, "a"): "// a", "a": 1})

    assert jd.data["a"] == 1
    assert jd.comments[Within(NONE, "a")] == "// a"
    assert list(jd.items()) == [(Within(NONE, "a"), "// a"), ("a", 1)]
    assert list(jd.items(comments=False)) == [("a", 1)]


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
    assert list(node.items(comments=False)) == [("x", 1)]


def test_items_default_keeps_within_and_comments_false_filters_recursively():
    jd = jsoncDict(
        {
            Within(NONE, "node"): "// head",
            "node": {
                "keep": 1,
                "hide": 2,
                Within("keep"): "/* slot */",
            },
            "tail": 3,
        }
    )
    jd["node"].comments["hide"] = {"reason": "runtime hidden"}

    assert list(jd.items()) == [
        (Within(NONE, "node"), "// head"),
        ("node", jd["node"]),
        ("tail", 3),
    ]
    assert list(jd.items(comments=False)) == [
        ("node", OrderedDict([("keep", 1)])),
        ("tail", 3),
    ]


def test_apply_permanently_removes_hidden_keys_recursively():
    jd = jsoncDict(
        {
            "node": {"keep": 1, "hide": 2},
            "tail": 3,
        }
    )
    jd["node"].comments["hide"] = {"reason": "runtime hidden"}

    jd.apply()

    assert jd.data["node"]["keep"] == 1
    assert "hide" not in jd.data["node"]
    assert list(jd["node"].items()) == [("keep", 1)]


def test_comments_get_supports_any_wildcard():
    jd = jsoncDict(
        {
            Within(NONE, "a"): "// before a",
            "a": 1,
            Within("a", "b"): "// between a and b",
            "b": 2,
            Within("a"): "/* slot a */",
            Within("b", NONE): "// after b",
        }
    )

    assert jd.comments_get(Within("a", Any)) == {
        Within("a", "b"): "// between a and b",
    }
    assert jd.comments_get(Within(Any, "b")) == {
        Within("a", "b"): "// between a and b",
    }
    assert jd.comments_get(Within(Any)) == {
        Within("a"): "/* slot a */",
    }


def test_comments_get_supports_ellipsis_neighbors():
    jd = jsoncDict(
        {
            Within(NONE, "a"): "// before a",
            "a": 1,
            Within("a", "b"): "// between a and b",
            "b": 2,
            Within("b"): "/* slot b */",
            Within("b", NONE): "// after b",
        }
    )

    assert jd.comments_get(Within("a", ...)) == {
        Within("a", "b"): "// between a and b",
    }
    assert jd.comments_get(Within("b", ...)) == {
        Within("b"): "/* slot b */",
        Within("b", NONE): "// after b",
    }
    assert jd.comments_get(Within(..., "b")) == {
        Within("a", "b"): "// between a and b",
    }


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
    jd = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps, slash_dash=False)
    child = jd.mixed()["list"]

    jd.data.rename_key("list", "items")

    assert jd.mixed()["items"] is child
    assert child.comments[Within(0, 1)] == "// 1,"


def test_jsonc_body_restore():
    jc = make_jsonc({"a": 1})
    assert '"a": 1' in jc.body


def test_loads_normalizes_slash_dash_key_without_conflict():
    raw = '{\n  "/-node": {\n    "x": 1\n  }\n}'
    jc = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps, slash_dash=True)

    assert "node" in jc.data
    assert "/-node" not in jc.data
    assert "node" in jc.comments
    assert jc.data["node"]["x"] == 1
    with pytest.raises(KeyError):
        jc["node"]


def test_loads_keeps_slash_dash_key_when_logical_key_conflicts():
    raw = '{\n  "/-node": 1,\n  "node": 2\n}'
    jc = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps, slash_dash=True)

    assert "/-node" in jc.data
    assert "node" in jc.data
    assert "node" not in jc.comments
    assert jc["/-node"] == 1
    assert jc["node"] == 2


def test_dumps_prefixes_marked_data_key_when_slash_dash_enabled():
    jc = jsoncDict({"node": {"x": 1}}, slash_dash=True)
    jc.comments["node"] = ""

    body = jc.body

    assert '"/-node": {' in body
    assert '"node": {' not in body


def test_dumps_marked_data_key_raises_todo_when_slash_dash_disabled():
    jc = jsoncDict({"node": {"x": 1}}, slash_dash=False)
    jc.comments["node"] = ""

    with pytest.raises(NotImplementedError, match=str(_TODO)):
        jc.body


def test_jsonc_dumps_restores_slot_and_between_comments():
    raw = '{\n  // head\n  "a" /*k*/ : /*cv*/ 1 /*vc*/,\n  "b": 2,\n  // list item\n  "list": [\n    0,\n    // 1,\n    2\n  ]\n}'
    jc = jsoncDict(raw, loads=hjson.loads, dumps=json_dumps)

    assert jc.comments[Within(NONE, "a")] == "// head"
    assert jc.comments[Within("a")] == {
        Within("k", ":"): "/*k*/",
        Within(":", "v"): "/*cv*/",
        Within("v", ","): "/*vc*/",
    }
    assert jc.comments[Within("b", "list")] == "// list item"
    assert list(jc["list"].items()) == [(0, 0), (Within(0, 1), "// 1,"), (1, 2)]

    body = jc.body

    assert '"a" /*k*/ :  /*cv*/ 1 /*vc*/' in body
    assert '\n  // head\n  "a"' in body
    assert '\n  // list item\n  "list"' in body
    assert '\n    // 1,\n    2\n' in body
