import json
from pathlib import Path

import hjson
import pytest

from jsonc_sdict.jsonc import hjsonDict, jsoncDict


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
    assert isinstance(jd, jsoncDict)


@pytest.mark.xfail(
    strict=True,
    raises=NameError,
    reason="jsonc.dumps/body restore path is still unfinished",
)
def test_jsonc_body_restore_is_not_ready():
    jc = make_jsonc({"a": 1})
    assert '"a": 1' in jc.body
