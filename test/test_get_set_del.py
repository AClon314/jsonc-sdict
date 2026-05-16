from types import SimpleNamespace

from jsonc_sdict.GetSetDel import del1, get1, set1
from jsonc_sdict.Sdict import sdict
from jsonc_sdict.share import NONE


def test_get1_returns_target_value():
    assert get1.item({"a": {"b": 1}}, ("a", "b")) == 1
    assert get1.item({"a": 1}, (), default="x") == {"a": 1}
    assert get1.attr(SimpleNamespace(a=SimpleNamespace(b=2)), ("a", "b")) == 2
    assert get1.ia({"node": SimpleNamespace(value=3)}, ("node", "value")) == 3


def test_set1_uses_pave_and_returns_previous_value_when_present():
    obj = {"a": {"b": 1}}
    assert set1.item(obj, ("a", "b"), 2) == 1
    assert obj == {"a": {"b": 2}}

    obj = {"a": {}}
    assert set1.item(obj, ("a", "b"), 2) == NONE
    assert obj == {"a": {"b": 2}}

    node = SimpleNamespace(value=3)
    obj = {"node": node}
    assert set1.ia(obj, ("node", "value"), 4) == 3
    assert node.value == 4

    paved = {}
    old = set1.item(paved, ("a", "b"), 1, pave=set1.pave_dict)
    assert old == NONE
    assert paved["a"] == {"b": 1}


def test_sdict_leaf_write_and_delete_helpers():
    obj = {"a": {"b": 1}}
    del1.item(obj, ("a", "b"))
    assert obj == {"a": {}}

    root = sdict({"a": {"b": 1}})
    set1.ia(root, ("a", "b"), 2)
    assert root["a"]["b"] == 2

    del1.ia(root, ("a", "b"))
    assert "b" not in root["a"]

    del1.ia(root, ("a",))
    assert "a" not in root
