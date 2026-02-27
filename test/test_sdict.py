import pytest
from jsonc_sdict.sdict import sdict  # as SDict
from share import get_caller


# class sdict(SDict):
#     def __getattribute__(self, name: str):
#         if name not in ("v", "data", "ref", "use_ref"):  # avoid recursion
#             pass
#             # try:
#             #     data = object.__getattribute__(self, "data") # avoid recursion
#             # except AttributeError:
#             #     data = self
#             # try:
#             #     ref = object.__getattribute__(self, "ref")
#             # except AttributeError:
#             #     ref = self
#             # print(self, *get_caller("jsonc_sdict.sdict"), sep="\t")
#         return super().__getattribute__(name)


def test_init_basic():
    d = sdict({"a": 1, "b": 2})
    assert d["a"] == 1
    assert d["b"] == 2
    assert isinstance(d, sdict)


def test_init_ref():
    data = [1, 2, 3]
    d = sdict(ref=data)
    assert d.ref == data
    assert d.v == data


def test_nested_access():
    d = sdict(
        {
            "user": {
                "info": {
                    "name": "Alex",
                    "address": {"city": "Shenzhen", "areas": ["Nanshan", "Baoan"]},
                }
            }
        }
    )

    assert d["user", "info", "name"] == "Alex"
    assert d["user", "info", "address", "areas", 0] == "Nanshan"
    assert d["user", "info", "address", "areas", 1] == "Baoan"
    assert isinstance(d["user", "info"], sdict)
    assert d["user", "info"]["name"] == "Alex"


def test_slice_access():
    d = sdict({"a": {"b": {"c": 1}}, "x": {"y": 2}})
    items = d[1:2]
    assert len(items) == 2
    assert all(isinstance(i, sdict) for i in items)
    assert set(i.keypath[-1][0] for i in items) == {"a", "x"}


def test_flat_iteration():
    data = {"a": 1, "b": {"c": 2, "d": [3, 4]}}
    d = sdict(data)

    flat_items = list(d.items_flat())
    depths = [v.depth for _, v in flat_items]
    assert 0 in depths
    assert 1 in depths

    keys = list(d.keys_flat())
    assert any(k == () for k in keys)
    assert any(k == ("b",) for k in keys)


def test_metadata():
    d = sdict({"a": {"b": 1}})
    root = d
    child_a = d["a"]

    assert root.depth == 0
    assert child_a.depth == 1
    assert child_a.parent[0] is root
    assert child_a.keypath == (["a"],)


def test_errors():
    d = sdict({"a": [1, 2]})

    with pytest.raises(KeyError):
        _ = d["non_existent"]

    with pytest.raises(IndexError):
        _ = d["a", 5]

    with pytest.raises(TypeError):
        _ = d["a", "invalid_key"]


# def test_rebuild():
#     d = sdict({"a": {"b": 1}})
#     # Bypassing logical methods and using OrderedDict updates directly
#     OrderedDict.__setitem__(d["a"], "c", 2)
#     d.rebuild()
#     assert d["a", "c"] == 2


def test_childkeys():
    d = sdict({"a": 1, "b": {"c": 2}})
    ck = d.childkeys
    assert len(ck) >= 1

    del d.childkeys
    assert "childkeys" not in d.__dict__
    new_ck = d.childkeys
    assert len(new_ck) >= 1


def test_insert():
    d = sdict({"a": 1, "c": 3})

    d.insert({"b": 2}, index=1)
    assert list(d.keys()) == ["a", "b", "c"]
    assert d["b"] == 2

    d.insert({"d": 4}, index=2)
    assert list(d.keys()) == ["a", "b", "d", "c"]
    assert d["d"] == 4

    d.insert({"e": 5}, index=4)
    assert list(d.keys()) == ["a", "b", "d", "c", "e"]
    assert d["e"] == 5

    d.insert({"c": 33}, index=0)
    assert list(d.keys()) == ["c", "a", "b", "d", "e"]
    assert d["c"] == 33


def test_index_and_find_key():
    d = sdict({"a": 10, "b": 20, "c": 30})

    assert d.index("b") == 1
    assert d.index(value=30) == 2
    with pytest.raises(ValueError):
        d.index("z")

    assert d.i_to_k(1) == "b"
    assert tuple(d.v_to_k(10))[0] == "a"
    assert d.i_to_k(-1) == "c"
    with pytest.raises(IndexError):
        d.i_to_k(10)


def test_sort():
    d = sdict({"c": 3, "a": 1, "b": 2})

    d.sort()
    assert list(d.keys()) == ["a", "b", "c"]

    d.sort(reverse=True)
    assert list(d.keys()) == ["c", "b", "a"]


def test_count():
    d = sdict({"a": 1, "b": 1, "c": 2})
    assert d.count(1) == 2
    assert d.count(2) == 1
    assert d.count(3) == 0


def test_rename_shallow_order_true_keeps_position():
    d = sdict({"a": 1, "b": 2, "c": 3})
    d.rename_key("b", "x", order=True)
    assert list(d.keys()) == ["a", "x", "c"]
    assert d["x"] == 2


def test_rename_shallow_order_false():
    d = sdict({"a": 1, "b": 2, "c": 3})
    d.rename_key("b", "x", order=False)
    assert "b" not in d
    assert d["x"] == 2


def test_rename_deep_with_cancel():
    d = sdict({"old": 0, "child": {"old": 1, "keep": 2}, "tail": {"old": 3}})
    g = d.rename_key("old", "new", deep=True)

    parent = next(g)
    assert parent is d
    parent = g.send(None)
    assert parent is d["child"]
    parent = g.send(False)
    assert parent is d["tail"]
    with pytest.raises(StopIteration):
        g.send(None)

    assert "old" not in d
    assert d["new"] == 0
    assert "old" in d["child"]
    assert "new" not in d["child"]
    assert "old" not in d["tail"]
    assert d["tail", "new"] == 3


def test_rename_re_shallow_with_str_patterns():
    d = sdict({"//a": 1, "//b": 2, "c": 3})
    d.rename_key_re(r"^//(.*)$", r"comment_\1")

    assert "//a" not in d
    assert "//b" not in d
    assert d["comment_a"] == 1
    assert d["comment_b"] == 2
    assert d["c"] == 3


def test_rename_re_deep_with_cancel():
    d = sdict({"//r": 0, "child": {"//r": 1}, "tail": {"//r": 2}})
    g = d.rename_key_re(r"^//(.*)$", r"@@\1", deep=True)

    parent = next(g)
    assert parent is d
    parent = g.send(None)
    assert parent is d["child"]
    parent = g.send(False)
    assert parent is d["tail"]
    with pytest.raises(StopIteration):
        g.send(None)

    assert "@@r" in d and "//r" not in d
    assert "//r" in d["child"] and "@@r" not in d["child"]
    assert "@@r" in d["tail"] and "//r" not in d["tail"]


def test_merge_conflict_old():
    d = sdict({"a": 1, "b": {"x": 1, "y": 2}})
    d.merge({"a": 9, "b": {"x": 10, "z": 3}, "c": 7}, conflict="old")

    assert d["a"] == 1
    assert d["b", "x"] == 1
    assert d["b", "y"] == 2
    assert d["b", "z"] == 3
    assert d["c"] == 7


def test_merge_conflict_new():
    d = sdict({"a": 1, "b": {"x": 1, "y": 2}})
    d.merge({"a": 9, "b": {"x": 10, "z": 3}, "c": 7}, conflict="new")

    assert d["a"] == 9
    assert d["b", "x"] == 10
    assert d["b", "y"] == 2
    assert d["b", "z"] == 3
    assert d["c"] == 7


def test_merge_conflict_manual_send():
    d = sdict({"a": 1, "b": {"x": 1}})
    g = d.merge({"a": 9, "b": {"x": 10}, "c": 7}, conflict=None)

    old_v, new_v, parent, key = next(g)
    assert (old_v, new_v, key) == (1, 9, "a")
    assert parent is d
    old_v, new_v, parent, key = g.send(5)
    assert (old_v, new_v, key) == (1, 10, "x")
    assert parent is d["b"]
    with pytest.raises(StopIteration):
        g.send(None)

    assert d["a"] == 5
    assert d["b", "x"] == 1
    assert d["c"] == 7


def test_merge_order_new():
    d = sdict({"a": 1, "b": {"x": 1, "y": 2}, "c": 3})
    d.merge({"c": 30, "a": 10, "b": {"y": 20, "x": 10}}, conflict="new", order="new")

    assert list(d.keys()) == ["c", "a", "b"]
    assert list(d["b"].keys()) == ["y", "x"]
