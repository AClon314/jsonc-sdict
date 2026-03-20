from types import MappingProxyType

import pytest

from jsonc_sdict.sdict import (
    del_item,
    del_item_attr,
    get_attr,
    get_item,
    get_item_attr,
    set_item,
    set_item_attr,
    sdict,
    unref,
)


@pytest.fixture(autouse=True)
def compat_sdict_cache():
    old = getattr(sdict, "_cached", None)
    sdict._cached = {"height", "childkeys", "unref"}
    yield
    if old is None:
        delattr(sdict, "_cached")
    else:
        sdict._cached = old


def make_sdict(data=None, **kwargs):
    kwargs.setdefault("deep", False)
    return sdict(data, **kwargs)


def test_nested_helper_accessors_work_on_dicts_and_objects():
    class Box:
        pass

    data = {"a": {"b": [1, {"c": 3}]}}
    root = Box()
    root.child = Box()
    root.child.value = 9

    assert get_item(data, ["a", "b", 1, "c"]) == 3
    assert get_attr(root, ["child", "value"]) == 9
    assert get_item_attr(root, ["child", "value"]) == 9
    assert get_item(data, ["missing"], default="fallback") == "fallback"


def test_nested_helper_mutators_work_in_place():
    class Box:
        pass

    data = {"a": {"b": 1}}
    root = Box()
    root.child = Box()
    root.child.value = 2
    root.child.extra = 3

    set_item(data, ["a", "b"], 7)
    set_item_attr(root, ["child", "value"], 8)
    assert data == {"a": {"b": 7}}
    assert root.child.value == 8

    del_item(data, ["a", "b"])
    del_item_attr(root, ["child", "extra"])
    assert data == {"a": {}}
    assert not hasattr(root.child, "extra")


def test_unref_handles_nested_sdict_and_const_mode():
    wrapped = {
        "left": make_sdict({"x": 1}),
        "right": [make_sdict({"y": 2}), 3],
    }

    assert unref(wrapped) == {"left": {"x": 1}, "right": [{"y": 2}, 3]}

    frozen = unref(make_sdict({"a": {"b": 1}, "arr": [2, 3]}), const=True)
    assert isinstance(frozen, MappingProxyType)
    assert isinstance(frozen["a"], MappingProxyType)
    assert frozen["arr"] == (2, 3)


def test_sdict_shallow_mapping_operations():
    data = make_sdict({"a": 1, "b": 2, "c": 2})

    assert data["a"] == 1
    assert data.index("b") == 1
    assert data.index(value=2) == 1
    assert data.count(2) == 2
    assert tuple(data.v_to_k(2)) == ("b", "c")

    data.insert({"x": 9}, key="a", after=True)
    assert list(data.keys()) == ["a", "x", "b", "c"]

    data.rename_key("x", "y")
    data.rename_key_re(r"^a$", "A")
    assert list(data.keys()) == ["A", "y", "b", "c"]

    data.sort(reverse=True)
    assert list(data.keys()) == ["y", "c", "b", "A"]


def test_sdict_ref_mode_reads_and_writes_nested_values():
    data = [{"a": 1}, [2, 3]]
    ref_view = make_sdict(ref=data)

    assert ref_view.use_ref is True
    assert ref_view.v is data
    assert ref_view[0, "a"] == 1
    assert ref_view[1, 0] == 2

    ref_view[1, 1] = 9
    assert data == [{"a": 1}, [2, 9]]


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason="deep rebuild still passes parent=... into sdict.__init__",
)
def test_sdict_deep_build_is_not_ready():
    sdict({"a": {"b": 1}})
