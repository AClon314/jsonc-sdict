from functools import partial
from types import MappingProxyType
from weakref import WeakKeyDictionary, WeakValueDictionary

from jsonc_sdict.sdict import (
    all_path,
    dictDict,
    del_item,
    del_item_attr,
    dfs,
    get_attr,
    get_item,
    get_item_attr,
    set_item,
    set_item_attr,
    sdict,
    un_dictDict,
    unref,
)
from jsonc_sdict.share import NONE, return_of


def test_nested_helper_accessors_work_on_dicts_and_objects():
    class Box:
        pass

    data = {"a": {"b": [1, {"c": 3}]}}
    root = Box()
    root.child = Box()
    root.child.value = 9

    assert get_item(data, ["a", "b", 1, "c"]) == 3
    assert partial(get_item, keys="a")({"a": 7}) == 7
    assert get_attr(root, ["child", "value"]) == 9
    assert get_item_attr(root, ["child", "value"]) == 9
    assert get_item(data, ["missing"], default="fallback") == "fallback"


def test_all_path_returns_node_key_dict_for_leaf_path():
    class Node:
        def __init__(self, name):
            self.name = name

        def __repr__(self):
            return self.name

    root = Node("root")
    mid = Node("mid")
    leaf = Node("leaf")
    graph = WeakKeyDictionary(
        {
            root: WeakValueDictionary({"a": mid}),
            mid: WeakValueDictionary({"b": leaf}),
        }
    )

    paths = list(all_path(graph))

    assert len(paths) == 1
    path = paths[0]
    assert list(path.items()) == [(root, "a"), (mid, "b"), (leaf, NONE)]
    assert list(path.nodePath) == [root, mid, leaf]
    assert list(path.keypath) == ["a", "b"]
    assert not hasattr(path, "cycleStartNode")


def test_all_path_keeps_root_and_child_order_for_multiple_roots():
    class Node:
        def __init__(self, name):
            self.name = name

        def __repr__(self):
            return self.name

    root1 = Node("root1")
    root2 = Node("root2")
    shared = Node("shared")
    leaf1 = Node("leaf1")
    leaf2 = Node("leaf2")
    graph = WeakKeyDictionary(
        {
            root1: WeakValueDictionary({"a": shared, "b": leaf1}),
            root2: WeakValueDictionary({"c": leaf2}),
            shared: WeakValueDictionary({"d": leaf2}),
        }
    )

    paths = list(all_path(graph))

    assert [[node.name for node in path.nodePath] for path in paths] == [
        ["root1", "shared", "leaf2"],
        ["root1", "leaf1"],
        ["root2", "leaf2"],
    ]
    assert [list(path.keypath) for path in paths] == [["a", "d"], ["b"], ["c"]]


def test_all_path_marks_cycle_start_without_appending_none_leaf():
    class Node:
        def __init__(self, name):
            self.name = name

        def __repr__(self):
            return self.name

    left = Node("left")
    right = Node("right")
    graph = WeakKeyDictionary(
        {
            left: WeakValueDictionary({"ab": right}),
            right: WeakValueDictionary({"ba": left}),
        }
    )

    paths = list(all_path(graph))

    assert len(paths) == 2

    first, second = paths
    assert list(first.items()) == [(left, "ab"), (right, "ba")]
    assert first.cycleStartNode() is left
    assert first.cycleStartKey == "ab"

    assert list(second.items()) == [(right, "ba"), (left, "ab")]
    assert second.cycleStartNode() is right
    assert second.cycleStartKey == "ba"


def test_all_path_with_target_returns_root_to_target_prefixes():
    class Node:
        def __init__(self, name):
            self.name = name

        def __repr__(self):
            return self.name

    root1 = Node("root1")
    root2 = Node("root2")
    shared = Node("shared")
    leaf = Node("leaf")
    graph = WeakKeyDictionary(
        {
            root1: WeakValueDictionary({"a": shared, "b": leaf}),
            root2: WeakValueDictionary({"c": shared}),
        }
    )

    paths = list(all_path(graph, target=shared))

    assert [list(path.items()) for path in paths] == [
        [(root1, "a"), (shared, NONE)],
        [(root2, "c"), (shared, NONE)],
    ]


def test_all_path_with_missing_target_returns_isolated_target_path():
    class Node:
        pass

    root = Node()
    leaf = Node()
    target = Node()
    graph = WeakKeyDictionary({root: WeakValueDictionary({"a": leaf})})

    paths = list(all_path(graph, target=target))

    assert len(paths) == 1
    assert list(paths[0].items()) == [(target, NONE)]


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
        "left": sdict({"x": 1}),
        "right": [sdict({"y": 2}), 3],
    }

    assert unref(wrapped) == {"left": {"x": 1}, "right": [{"y": 2}, 3]}

    frozen = unref(sdict({"a": {"b": 1}, "arr": [2, 3]}), const=True)
    assert isinstance(frozen, MappingProxyType)
    assert isinstance(frozen["a"], MappingProxyType)
    assert frozen["arr"] == (2, 3)


def test_unref_preserves_shared_references_and_cycles():
    shared = sdict({"x": 1}, deep=False)
    wrapped = {"left": shared, "right": shared}

    plain = unref(wrapped)

    assert plain == {"left": {"x": 1}, "right": {"x": 1}}
    assert plain["left"] is plain["right"]

    cyc = {}
    cyc["self"] = cyc
    restored = unref(cyc)

    assert restored["self"] is restored


def test_un_dictDict_restores_nested_and_root_lists():
    nested = {
        "groups": [
            {
                "id": "g1",
                "children": [
                    {"id": "c1", "name": "left"},
                    {"id": "c2", "name": "right"},
                ],
            },
            {"id": "g2", "children": []},
        ],
        "keep": {"value": 1},
    }
    nested_ctx = return_of(
        dictDict(dfs(nested), value_of_idKey=partial(get_item, keys="id"))
    )
    nested_restored = un_dictDict(nested_ctx)
    assert unref(nested_restored) == nested

    root = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    root_ctx = return_of(
        dictDict(dfs(root), value_of_idKey=partial(get_item, keys="id"))
    )
    root_restored = un_dictDict(root_ctx)
    assert unref(root_restored) == root


def test_sdict_shallow_mapping_operations_smoke():
    data = sdict({"a": 1, "b": 2, "c": 2})

    data.insert({"x": 9}, key="a", after=True)
    data.rename_key("x", "y")
    data.rename_key_re(r"^a$", "A")
    data.sort(reverse=True)

    assert list(data.items()) == [("y", 9), ("c", 2), ("b", 2), ("A", 1)]


def test_sdict_merge_merges_into_self_and_forwards_kwargs():
    data = sdict({"children": [{"id": 1, "name": "1", "old": None}]})

    result = data.merge(
        {"children": [{"id": 1, "name": "2", "new": ""}, {"id": 2, "name": "3"}]},
        dictDict={"value_of_idKey": partial(get_item, keys="id")},
        unMergeable="new",
    )

    assert result is data
    assert data.equal(
        {
            "children": [
                {"id": 1, "name": "2", "old": None, "new": ""},
                {"id": 2, "name": "3"},
            ]
        }
    )


def test_sdict_ref_mode_reads_and_writes_nested_values():
    data = [{"a": 1}, [2, 3]]
    ref_view = sdict(ref=data)

    assert ref_view.use_ref is True
    assert ref_view.v is data
    assert ref_view[0, "a"] == 1
    assert ref_view[1, 0] == 2

    ref_view[1, 1] = 9
    assert data == [{"a": 1}, [2, 9]]


def test_sdict_init_deep_builds_nested_sdict():
    data = sdict({"a": {"b": 1}})

    assert isinstance(data["a"], sdict)
    assert data["a", "b"] == 1


def test_sdict_rebuild_wraps_nested_mapping_after_shallow_init():
    data = sdict({"a": {"b": 1}}, deep=False)

    assert isinstance(data["a"], dict)

    data.rebuild()

    assert isinstance(data["a"], sdict)


def test_sdict_getitem_slice_returns_flattened_descendants():
    data = sdict({"a": {"b": 1}, "x": {"y": 2}}, deep=False)
    values = data[1:]

    assert [value.v for value in values] == [{"b": 1}, {"y": 2}]


def test_sdict_del_cache_keeps_requested_keypath_cache():
    data = sdict({"a": {"b": 1}})
    child = data["a"]

    assert "keypath" in child.__dict__

    child.del_cache(without=("keypath",))

    assert child.keypath == ("a",)
    assert "keypath" in child.__dict__

    child.del_cache()

    assert "keypath" not in child.__dict__


def test_sdict_v_returns_self_in_data_mode():
    data = sdict({"a": 1}, deep=False)

    assert data.v is data


def test_sdict_unref_property_returns_plain_nested_data():
    data = sdict({"a": {"b": 1}})

    assert data.unref() == {"a": {"b": 1}}


def test_sdict_is_nestKeys_excludes_strings():
    assert sdict.is_nestKeys(("a", "b")) is True
    assert sdict.is_nestKeys("ab") is False


def test_sdict_getitem_method_returns_default_for_missing_path():
    data = sdict({"a": {"b": 1}}, deep=False)

    assert data.getitem(["a", "missing"], default="fallback") == "fallback"


def test_sdict_setitem_method_updates_nested_value():
    data = sdict({"a": {"b": 1}}, deep=False)

    data.setitem(["a", "b"], 2)

    assert data["a"]["b"] == 2


def test_sdict_dunder_setitem_updates_nested_value():
    data = sdict({"a": {"b": 1}}, deep=False)

    data["a", "b"] = 3

    assert data["a"]["b"] == 3


def test_sdict_delitem_method_deletes_nested_value():
    data = sdict({"a": {"b": 1}}, deep=False)

    data.delitem(["a", "b"])

    assert data == {"a": {}}


def test_sdict_dunder_delitem_deletes_nested_value():
    data = sdict({"a": {"b": 1}}, deep=False)

    del data["a", "b"]

    assert data == {"a": {}}


def test_sdict_hash_uses_identity():
    data = sdict({"a": 1}, deep=False)

    assert hash(data) == id(data)


def test_sdict_repr_obeys_repr_flag():
    data = sdict({"a": 1}, deep=False)

    assert repr(data) == "{'a': 1}"

    data.repr = True

    assert repr(data) == "sdict({'a': 1})"


def test_sdict_ior_mutates_in_place():
    data = sdict({"a": 1}, deep=False)

    result = data
    result |= {"b": 2}

    assert result is data
    assert data == {"a": 1, "b": 2}


def test_sdict_pop_removes_key():
    data = sdict({"a": 1, "b": 2}, deep=False)

    data.pop("a")

    assert list(data.items()) == [("b", 2)]


def test_sdict_popitem_removes_last_pair():
    data = sdict({"a": 1, "b": 2}, deep=False)

    data.popitem(last=True)

    assert list(data.items()) == [("a", 1)]


def test_sdict_update_merges_mapping():
    data = sdict({"a": 1}, deep=False)

    data.update({"b": 2})

    assert data == {"a": 1, "b": 2}


def test_sdict_clear_empties_mapping():
    data = sdict({"a": 1}, deep=False)

    data.clear()

    assert data == {}


def test_sdict_are_equal_respects_key_order():
    left = sdict({"b": 2, "a": 1}, deep=False)

    assert sdict.are_equal(left, {"b": 2, "a": 1}) is True
    assert sdict.are_equal(left, {"a": 1, "b": 2}) is False


def test_sdict_equal_respects_key_order():
    data = sdict({"b": 2, "a": 1}, deep=False)

    assert data.equal({"b": 2, "a": 1}) is True
    assert data.equal({"a": 1, "b": 2}) is False


def test_sdict_rename_key_replaces_key_name():
    data = sdict({"a": 1, "b": 2}, deep=False)

    data.rename_key("a", "A")

    assert list(data.items()) == [("A", 1), ("b", 2)]


def test_sdict_rename_key_re_applies_regex_substitution():
    data = sdict({"aa": 1, "ab": 2}, deep=False)

    data.rename_key_re(r"^a", "z")

    assert list(data.items()) == [("za", 1), ("zb", 2)]


def test_sdict_rename_key_deep_updates_nested_mappings():
    data = sdict({"a": {"old": 1}, "b": {"old": 2}}, deep=False)

    data.rebuild()
    data.rename_key("old", "new", deep=True)

    assert data.unref() == {"a": {"new": 1}, "b": {"new": 2}}


def test_sdict_rename_key_without_old_renames_current_node_in_parent():
    data = sdict({"a": {"value": 1}, "b": {"value": 2}}, deep=False)

    data.rebuild()
    data["a"].rename_key(new="renamed")

    assert list(data.keys()) == ["renamed", "b"]
    assert data["renamed", "value"] == 1


def test_sdict_keys_flat_digLeaf():
    data = sdict({"a": {"b": 1}}, deep=False)

    assert list(data.keys_flat(readonly=True, digLeaf=True)) == [("a", "b")]


def test_sdict_values_flat_notDigLeaf():
    data = sdict({"a": {"b": 1}}, deep=False)
    values = list(data.values_flat(readonly=True, digLeaf=False))

    assert [value.v for value in values] == [{"b": 1}]


def test_sdict_leaves():
    data = sdict({"a": {"b": {"c": 1}}, "b": {"c": 2}}, deep=False)
    items = list(data.leaves)

    # NOTE: valve.v because deep==False
    assert [(key, value.v) for key, value in items] == [
        (("a", "b"), {"c": 1}),
        (("b",), {"c": 2}),
    ]


def test_sdict_items_flat_digLeaf():
    data = sdict({"a": {"b": {"c": 1}}, "b": {"c": 2}}, deep=False)
    items = list(data.items_flat(readonly=True, digLeaf=True))

    assert [(key, value) for key, value in items] == [
        (("a", "b", "c"), 1),
        (("b", "c"), 2),
    ]


def test_sdict_items_flat_slice_supports_negative_depth_index():
    data = sdict({"a": {"b": {"c": 1}}, "b": {"c": 2}}, deep=False)
    items = list(data.items_flat(readonly=True, digLeaf=False, slice=slice(-1, None)))

    assert [(key, value.v) for key, value in items] == [
        (("a", "b"), {"c": 1}),
    ]


def test_sdict_dfs_readonly_yields_nested_nodes():
    data = sdict({"a": {"b": 1}}, deep=False)
    nodes = list(data.dfs(readonly=True))

    assert [node.v for node in nodes] == [{"a": {"b": 1}}, {"b": 1}]
    assert nodes[1].keypath == ("a",)


def test_sdict_insert_by_index_places_items_before_target():
    data = sdict({"a": 1, "c": 3}, deep=False)

    data.insert({"b": 2}, index=1)

    assert list(data.items()) == [("a", 1), ("b", 2), ("c", 3)]


def test_sdict_index_finds_key_and_value_positions():
    data = sdict({"a": 1, "b": 2}, deep=False)

    assert data.index("b") == 1
    assert data.index(value=2) == 1


def test_sdict_i_to_k_returns_key_for_index():
    data = sdict({"a": 1, "b": 2}, deep=False)

    assert data.i_to_k(1) == "b"


def test_sdict_v_to_k_yields_all_matching_keys():
    data = sdict({"a": 1, "b": 2, "c": 2}, deep=False)

    assert tuple(data.v_to_k(2)) == ("b", "c")


def test_sdict_sort_orders_keys_with_callable():
    data = sdict({"bbb": 1, "a": 2, "cc": 3}, deep=False)

    data.sort(key=len)

    assert list(data.keys()) == ["a", "cc", "bbb"]


def test_sdict_count_counts_matching_values():
    data = sdict({"a": 1, "b": 2, "c": 2}, deep=False)

    assert data.count(2) == 2


def test_sdict_keypath_reports_node_path():
    data = sdict({"a": {"b": 1}})

    assert data["a"].keypath == ("a",)


def test_sdict_keypaths_are_derived_from_fork_graph():
    data = sdict({"a": {"b": 1}})

    assert list(data["a"].keypaths) == [("a",)]
    assert isinstance(data.forkGraph, WeakKeyDictionary)


def test_sdict_in_edges_and_parents_are_derived_from_fork_graph():
    shared = sdict({"b": 1}, deep=False)
    data = sdict({"a": shared, "x": shared}, deep=False)
    data.rebuild()

    edges = list(data["a"]._parentWithKey)

    assert edges == [(data, "a"), (data, "x")]
    assert tuple(data["a"].parents) == (data,)


def test_sdict_dfs_stops_on_cycle_without_losing_direct_child():
    left = sdict({}, deep=False)
    right = sdict({}, deep=False)
    left["b"] = right
    right["a"] = left

    nodes = list(left.dfs())

    assert nodes == [left, right]


def test_sdict_parent_reports_parent_node():
    data = sdict({"a": {"b": 1}})

    assert data["a"].parent is data


def test_sdict_roots_deduplicates_same_root_for_shared_node():
    shared = sdict({"b": 1}, deep=False)
    data = sdict({"a": shared, "x": shared}, deep=False)
    data.rebuild()

    assert tuple(data["a"].roots) == (data,)


def test_sdict_depth_reports_node_depth():
    data = sdict({"a": {"b": 1}})

    assert data["a"].depth == 1


def test_sdict_childkeys_returns_root_and_direct_children():
    data = sdict({"a": {"b": 1}})

    assert len(data.childkeys) == 2
    assert data.childkeys[1].parent is data


def test_sdict_child_caches_are_invalidated_after_top_level_mutation():
    data = sdict({"a": {"b": 1}})

    assert data.unref() == {"a": {"b": 1}}
    assert len(data.childkeys) == 2

    data["x"] = {"y": 2}

    assert data.unref() == {"a": {"b": 1}, "x": {"y": 2}}
    assert [node.keypath for node in data.childkeys] == [(), ("a",), ("x",)]


def test_sdict_dfs_default_mode_yields_nested_nodes():
    data = sdict({"a": {"b": 1}}, deep=False)
    nodes = list(data.dfs())

    assert [node.v for node in nodes] == [{"a": {"b": 1}}, {"b": 1}]
    assert nodes[1].keypath == ("a",)


def test_sdict_dfs_on_child_keeps_absolute_keypath():
    data = sdict({"a": {"b": {"c": 1}}})
    nodes = list(data["a"].dfs())

    assert nodes == [data["a"], data["a", "b"]]
    assert [node.keypath for node in nodes] == [("a",), ("a", "b")]


def test_sdict_height_reports_max_nested_depth():
    assert sdict({"a": {"b": 1}}, deep=False).height == 1


def test_sdict_deepests_reports_deepest_descendants_from_current_node():
    data = sdict({"a": {"b": 1}, "x": {"y": {"z": 2}}})

    assert tuple(node.unref() for node in data.deepests) == ({"z": 2},)
    assert data["a"].deepest is data["a"]
    assert data["x"].deepest is data["x", "y"]
