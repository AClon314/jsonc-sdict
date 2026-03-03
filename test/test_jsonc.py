import json
from pathlib import Path
from collections import OrderedDict

import hjson

from jsonc_sdict.jsonc import AS_DATA, jsonc
from jsonc_sdict.share import getLogger

Log = getLogger(__name__)
Log.setLevel("DEBUG")


def test_setitem_comment_key_seed_and_data_escape():
    seed = "-S"
    jc = jsonc(seed=seed)

    jc["//line"] = "hello"
    jc["/*block"] = "world"
    jc["//raw" + AS_DATA] = 1

    assert "//line-S" in jc
    assert "/*block-S" in jc
    assert "//raw" in jc
    assert jc.is_comment("//line-S") == "//line"
    assert jc.is_comment("//raw") == ""


def test_to_inner_key_batch_converts_deep_prefixes_and_as_data():
    jc = jsonc(
        {
            "root": {
                "//line": 1,
                "/*blk": 2,
                "/-node": {"x": 3},
                "//real" + AS_DATA: 4,
            }
        },
        identify_commentKey=False,
    )
    seed = jc.SEED

    root = OrderedDict.__getitem__(jc, "root")
    assert list(root.keys()) == ["//line", "/*blk", "/-node", "//real" + AS_DATA]

    jc.to_inner_key_batch()
    root = OrderedDict.__getitem__(jc, "root")
    assert list(root.keys()) == [
        f"//line{seed}",
        f"/*blk{seed}",
        f"/-node{seed}",
        "//real",
    ]

    # default init path should not produce duplicated SEED suffix
    jc2 = jsonc({"root": {"//line": 1}})
    seed2 = jc2.SEED
    root2 = OrderedDict.__getitem__(jc2, "root")
    assert list(root2.keys()) == [f"//line{seed2}"]


def test_bake_parses_comments_into_data_and_keeps_edges():
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

    jc = jsonc()
    body = jc.bake(text)
    parsed = json.loads(body)
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

    arr = OrderedDict.__getitem__(jc, "arr")
    assert isinstance(arr, list)
    assert any(
        isinstance(x, dict)
        and len(x) == 1
        and next(iter(x)).startswith("//")
        and next(iter(x)).endswith(jc.SEED)
        for x in arr
    )


def test_body_cache_refresh_on_mutation_and_body_setter():
    jc = jsonc({"a": 1})

    body_before = jc.body
    assert '"a": 1' in body_before

    jc["b"] = 2
    body_after = jc.body
    assert body_before != body_after
    assert '"b": 2' in body_after

    jc.body = {"x": 9}
    assert list(jc.keys()) == ["x"]
    assert jc["x"] == 9


def test_body_restored_and_full():
    jc = jsonc()
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

    restored = jc.body_restored

    assert "//line" in restored
    assert '"/-node": {' in restored
    assert "/*block*/" in restored
    assert '"a": 1' in restored
    assert jc.full == jc.header + restored + jc.footer

    # restored text should still keep data-keys in body output
    parsed_body = json.loads(jc.body)
    assert f"//c{seed}" in parsed_body


def test_readme_example():
    base = Path(__file__).parent
    old_path = base / "old.jsonc"
    new_path = base / "new.jsonc"

    text = old_path.read_text(encoding="utf-8")
    jc = jsonc()
    parsed = json.loads(jc.bake(text))
    Log.debug(f"{jc=}")
    jc.body = parsed
    Log.debug(f"{jc=}")

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
    Log.debug(f"{jc=}")

    out = jc.full
    new_path.write_text(out, encoding="utf-8")

    # single-line comments
    assert "//my comment but at end of body" in out
    assert "//my line-above comments" in out
    # multi-line(block) comment
    assert "/*my multi-\n  line comments\n  */" in out
    # AS_DATA-suffixed key should remain a normal data key
    assert '"//your data key overlap with comment-keyname rule?"' in out
    # line-above comment should appear before key "2"
    assert out.find("//my line-above comments") < out.find('"2": 2')


def test_readme_example_2():
    base = Path(__file__).parent
    old_path = base / "old.jsonc"
    new_path = base / "new.jsonc"

    text = old_path.read_text(encoding="utf-8")
    jc = jsonc(hjson.loads(text), text)
    parsed = json.loads(jc.body)
    Log.debug(f"{jc=}")
    jc.body = parsed
    Log.debug(f"{jc=}")

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
    Log.debug(f"{jc=}")

    out = jc.full
    new_path.write_text(out, encoding="utf-8")

    # single-line comments
    assert "//my comment but at end of body" in out
    assert "//my line-above comments" in out
    # multi-line(block) comment
    assert "/*my multi-\n  line comments\n  */" in out
    # AS_DATA-suffixed key should remain a normal data key
    assert '"//your data key overlap with comment-keyname rule?"' in out
    # line-above comment should appear before key "2"
    assert out.find("//my line-above comments") < out.find('"2": 2')
