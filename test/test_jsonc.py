import json
from pathlib import Path
from typing import cast

import hjson
import pytest

from jsonc_sdict.jsonc import AS_DATA, jsoncDict, hjsonDict
from jsonc_sdict.share import getLogger

Log = getLogger(__name__)
Log.setLevel("DEBUG")


def _dumps(obj, **kwargs):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def Jsonc(raw, **kwargs):
    return jsoncDict(raw, hjson.loads, dumps=_dumps, **kwargs)


def Hjson(raw, **kwargs):
    return hjsonDict(raw, hjson.loads, dumps=_dumps, **kwargs)


def test_setitem_comment_key_seed_and_data_escape():
    seed = "-S"
    jc = Jsonc({}, seed=seed)

    jc["//line"] = "hello"
    jc["/*block"] = "world"
    jc["//raw" + AS_DATA] = 1

    assert "//line-S" in jc
    assert "/*block-S" in jc
    assert "//raw" in jc
    line_comment = jc.split_keyname("//line-S")
    assert line_comment is not None
    assert str(line_comment) == "//line"
    assert jc.split_keyname("//raw") is None


def test_to_inner_key_batch_converts_deep_prefixes_and_as_data():
    jc = Jsonc(
        {
            "root": {
                "//line": 1,
                "/*blk": 2,
                "/-node": {"x": 3},
                "//real" + AS_DATA: 4,
            }
        },
        init_commentKey=False,
    )
    seed = jc.SEED

    root = dict.__getitem__(cast(dict[str, object], jc), "root")
    assert isinstance(root, dict)
    assert list(root.keys()) == ["//line", "/*blk", "/-node", "//real" + AS_DATA]

    jc.to_inner_key_batch(jc.dumps())
    root = dict.__getitem__(cast(dict[str, object], jc), "root")
    assert isinstance(root, dict)
    assert list(root.keys()) == [
        f"//line{seed}",
        f"/*blk{seed}",
        f"/-node{seed}",
        "//real",
    ]

    # default init path (flat key) should not produce duplicated SEED suffix
    jc2 = Jsonc({"//line": 1})
    seed2 = jc2.SEED
    assert list(jc2.keys()) == [f"//line{seed2}"]


def test_loads_parses_comments_into_data_and_keeps_edges():
    text = (
        "// head\n"
        "{\n"
        '  "a": 1, // a\n'
        '  /* b */"b": 2,\n'
        '  "arr": [1, // x\n'
        "    2]\n"
        "}\n"
        "// tail\n"
    )

    jc = Jsonc({})
    body = jc.loads(text)
    parsed = json.loads(body)
    jc.clear()
    jc.update(parsed)

    assert jc.header == "// head\n"
    assert jc.footer == "\n// tail\n"
    assert isinstance(body, str)
    assert jc["a"] == 1
    assert jc["b"] == 2

    root_comment_keys = [
        k for k in jc.keys() if isinstance(k, str) and k.endswith(jc.SEED)
    ]
    assert any(k.startswith("//") for k in root_comment_keys)
    assert any(k.startswith("/*") for k in root_comment_keys)

    arr = dict.__getitem__(cast(dict[str, object], jc), "arr")
    assert isinstance(arr, list)
    found_comment_item = False
    for x in arr:
        if not (isinstance(x, dict) and len(x) == 1):
            continue
        key = next(iter(x))
        if isinstance(key, str) and key.startswith("//") and key.endswith(jc.SEED):
            found_comment_item = True
            break
    assert found_comment_item


def test_body_cache_refresh_on_mutation_and_body_setter():
    jc = Jsonc({"a": 1})
    jc.del_cache()

    body_before = jc.body
    assert '"a": 1' in body_before

    jc["b"] = 2
    body_after = jc.body
    assert body_before != body_after
    assert '"b": 2' in body_after

    jc.clear()
    jc.update({"x": 9})
    assert list(jc.keys()) == ["x"]
    assert '"x": 9' in jc.body


def test_body_restored_and_full():
    jc = Jsonc({})
    seed = jc.SEED
    jc.update(
        {
            f"//c{seed}": "line",
            f"/-node{seed}": {"x": 1},
            "a": 1,
            "arr": [{f"/*0{seed}": "block"}, 2],
        }
    )
    jc.header = "// H\n"
    jc.footer = "\n// F"

    restored = jc.body

    assert "//line" in restored
    assert '"/-node": {' in restored
    assert "/*block*/" in restored
    assert '"a": 1' in restored
    assert jc.full == jc.header + restored + jc.footer

    # internal data-keys are still preserved in mapping
    assert f"//c{seed}" in jc


@pytest.mark.parametrize(
    "old_name,new_name,initFunc,expected_block",
    [
        (
            "old.jsonc",
            "new-from_jsonc.jsonc",
            Jsonc,
            "/*my multi-\n  line comments\n  */",
        ),
        ("old.hjson", "new-from_hjson.hjson", Hjson, "/*my multi-\nline comments\n*/"),
    ],
)
def test_readme_example(old_name: str, new_name: str, initFunc, expected_block: str):
    base = Path(__file__).parent
    new_path = base / new_name

    text = (base / old_name).read_text(encoding="utf-8")
    jc: jsoncDict = initFunc(text)
    Log.debug(f"{list(jc.keys())=}")

    # end-of-body single-line comment
    jc["//unique-keyname"] = "my comment but at end of body"

    # line-above + multi-line comment + AS_DATA escape key
    jc.insert_comment(
        {
            "/*\nunique-keyname-1": "my multi-\nline comments\n",
            "//\nunique-keyname-2": "my line-above comments\n",
            "//your data key overlap with comment-keyname rule?" + AS_DATA: [
                "treat as data, not comment"
            ],
        },
        key="2",
    )
    Log.debug(f"keys after insert: {list(jc.keys())}")

    out = jc.full
    new_path.write_text(out, encoding="utf-8")

    # single-line comments
    assert "//my comment but at end of body" in out
    assert "//my line-above comments" in out
    # multi-line(block) comment
    assert expected_block in out
    # AS_DATA-suffixed key should remain a normal data key
    assert '"//your data key overlap with comment-keyname rule?"' in out
    # line-above comment should appear before key "2"
    assert out.find("//my line-above comments") < out.find('"2": 2')
    # existing source comments should still be preserved
    assert '// "": null,' in out
    assert "/* 2 */" in out
    if old_name == "old.hjson":
        assert not out.lstrip().startswith("{")
        assert '"10": "# is single line in hjson" # comment' in out
        assert "\n// end of body" in out
