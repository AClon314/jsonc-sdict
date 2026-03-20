import json

import hjson
import pytest

from jsonc_sdict.jsonc import hjsonDict, jsoncDict
from jsonc_sdict.sdict import sdict


@pytest.fixture(autouse=True)
def compat_jsonc_cache():
    old_sdict = getattr(sdict, "_cached", None)
    old_jsonc = getattr(jsoncDict, "_cached", None)
    old_hjson = getattr(hjsonDict, "_cached", None)
    sdict._cached = {"height", "childkeys", "unref"}
    jsoncDict._cached = {"height", "childkeys", "unref", "body", "data"}
    hjsonDict._cached = {"height", "childkeys", "unref", "body", "data"}
    yield
    if old_sdict is None:
        delattr(sdict, "_cached")
    else:
        sdict._cached = old_sdict
    if old_jsonc is None:
        delattr(jsoncDict, "_cached")
    else:
        jsoncDict._cached = old_jsonc
    if old_hjson is None:
        delattr(hjsonDict, "_cached")
    else:
        hjsonDict._cached = old_hjson


def json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def make_jsonc(raw, **kwargs):
    kwargs.setdefault("deep", False)
    return jsoncDict(raw, hjson.loads, dumps=json_dumps, **kwargs)


def make_hjson(raw, **kwargs):
    kwargs.setdefault("deep", False)
    return hjsonDict(raw, hjson.loads, dumps=json_dumps, **kwargs)


def test_split_key_detects_comment_markers():
    inline = jsoncDict.split_key("//line")
    line_above = jsoncDict.split_key("//\nline")
    block = jsoncDict.split_key("/*\nblock")

    assert inline is not None
    assert inline.prefix == "//"
    assert inline.before == ""
    assert str(inline) == "//line"

    assert line_above is not None
    assert line_above.prefix == "//"
    assert line_above.before == "\n"

    assert block is not None
    assert block.prefix == "/*"
    assert block.before == "\n"
    assert jsoncDict.split_key("plain") is None


def test_hjson_split_key_supports_hash_comments():
    comment = hjsonDict.split_key("# hello")
    assert comment is not None
    assert comment.prefix == "#"
    assert str(comment) == "# hello"


def test_mapping_init_keeps_comment_like_keys_and_insert_reorders_comments():
    jc = make_jsonc({"a": 1, "//tail": "line"})

    assert list(jc.keys()) == ["a", "//tail"]
    assert jc.forceDataKeys == set()

    jc.insert({"//before": "head", "b": 2}, key="a", after=True)
    assert list(jc.keys()) == ["//before", "b", "a", "//tail"]


def test_insert_has_comment_false_records_forced_data_keys():
    jc = make_jsonc({"a": 1})

    jc.insert({"//literal": 3}, key="a", after=True, has_comment=False)

    assert jc.forceDataKeys == {"//literal"}
    assert jc["//literal"] == 3
    assert list(jc.keys()) == ["a", "//literal"]


@pytest.mark.xfail(
    strict=True,
    raises=NameError,
    reason="jsonc.loads(raw_text) parser rewrite is still unfinished",
)
def test_jsonc_loads_from_text_is_not_ready():
    make_jsonc("// head\n{\n  \"a\": 1\n}\n")


@pytest.mark.xfail(
    strict=True,
    raises=NameError,
    reason="jsonc.dumps/body restore path is still unfinished",
)
def test_jsonc_body_restore_is_not_ready():
    jc = make_jsonc({"a": 1})
    assert '"a": 1' in jc.body
