from functools import partial

import pytest
from deepdiff import DeepDiff as RawDeepDiff

from jsonc_sdict.GetSetDel import get1
from jsonc_sdict.Merge import DeepDiffProtocol, merge
from jsonc_sdict.share import are_equal


def test_merge_module_helpers_import_cleanly():
    assert issubclass(DeepDiffProtocol, object)
    assert getattr(DeepDiffProtocol, "_is_protocol", False) is True
    assert callable(merge.get_item)


def test_merge_basic():
    t1 = {
        "list-no^": [1, 2],
        "list^": [1, 2],
        "dict^": {"dict-no^": {0: 1}, "^": 0},
        "dict-easy": {0: 0},
    }
    t2 = {
        "list-no^": [3, 4],
        "list^": [1, 3],
        "dict^": {"^": 0, "dict-no^": {1: 2}},
        "dict-easy": {0: 0, 1: 1},
    }

    merged = merge((t1, t2), dictDict=None).solve_all().merged
    should = {
        "list-no^": [1, 2, 3, 4],
        "list^": [1, 2, 3],
        "dict^": {"dict-no^": {0: 1, 1: 2}, "^": 0},
        "dict-easy": {0: 0, 1: 1},
    }
    assert are_equal(merged, should)


def test_merge_dictDict():
    l1 = [
        {"id": 1, "name": "1", "old": None},
        {"id": 2, "name": "2"},
        {"id": 3, "name": "3"},
    ]
    l2 = [
        {"id": 2, "name": "1", "new": ""},
        {"id": 1, "name": "2"},
        {"id": 3, "name": "3"},
    ]
    t1 = {"children": l1}
    t2 = {"children": l2, "k": "v"}

    merged = (
        merge(
            (t1, t2),
            dictDict={"value_of_idKey": partial(get1.item, keys="id")},
            unMergeable="new",
            mergeable=merge.mergeable_prefer_new,
        )
        .solve_all()
        .merged
    )
    should = {
        "children": [
            {"id": 1, "name": "2", "old": None},
            {"id": 2, "name": "1", "new": ""},
            {"id": 3, "name": "3"},
        ],
        "k": "v",
    }
    assert are_equal(merged, should)


def test_merge_dictionary_item_removed_respects_container_preference():
    old = {"api": {"groupId": {"projectId_1": {"": {"title": "XX项目"}}}}}
    new = {"api": {}}

    keep_old = merge((old, new), mergeable=merge.mergeable_prefer_old).solve_all().merged
    keep_new = merge((old, new), mergeable=merge.mergeable_prefer_new).solve_all().merged

    assert keep_old == old
    assert keep_new == new


def test_merge_dictionary_item_added_respects_container_preference():
    old = {"api": {}}
    new = {"api": {"groupId": {"projectId_1": {"": {"title": "XX项目"}}}}}

    keep_old = merge((old, new), mergeable=merge.mergeable_prefer_old).solve_all().merged
    keep_new = merge((old, new), mergeable=merge.mergeable_prefer_new).solve_all().merged

    assert keep_old == old
    assert keep_new == new


def test_merge_iterable_item_add_remove_respects_preference():
    keep_old = merge(RawDeepDiff([1], [1, 2], view="tree")).solve_all().merged
    keep_new = merge(
        RawDeepDiff([1], [1, 2], view="tree"), unMergeable="new"
    ).solve_all().merged
    removed_old = merge(RawDeepDiff([1, 2], [1], view="tree")).solve_all().merged
    removed_new = merge(
        RawDeepDiff([1, 2], [1], view="tree"), unMergeable="new"
    ).solve_all().merged

    assert keep_old == [1]
    assert keep_new == [1, 2]
    assert removed_old == [1, 2]
    assert removed_new == [1]


def test_merge_set_item_add_remove_respects_preference():
    keep_old = merge(RawDeepDiff({1}, {1, 2}, view="tree")).solve_all().merged
    keep_new = merge(
        RawDeepDiff({1}, {1, 2}, view="tree"), unMergeable="new"
    ).solve_all().merged
    removed_old = merge(RawDeepDiff({1, 2}, {1}, view="tree")).solve_all().merged
    removed_new = merge(
        RawDeepDiff({1, 2}, {1}, view="tree"), unMergeable="new"
    ).solve_all().merged

    assert keep_old == {1}
    assert keep_new == {1, 2}
    assert removed_old == {1, 2}
    assert removed_new == {1}


def test_merge_attribute_add_remove_respects_preference():
    class Obj:
        pass

    def make_add_pair():
        old = Obj()
        old.a = 1
        new = Obj()
        new.a = 1
        new.b = 2
        return old, new

    def make_remove_pair():
        old = Obj()
        old.a = 1
        old.b = 2
        new = Obj()
        new.a = 1
        return old, new

    keep_old = merge(RawDeepDiff(*make_add_pair(), view="tree")).solve_all().merged
    keep_new = merge(
        RawDeepDiff(*make_add_pair(), view="tree"), unMergeable="new"
    ).solve_all().merged
    removed_old = merge(RawDeepDiff(*make_remove_pair(), view="tree")).solve_all().merged
    removed_new = merge(
        RawDeepDiff(*make_remove_pair(), view="tree"), unMergeable="new"
    ).solve_all().merged

    assert not hasattr(keep_old, "b")
    assert keep_new.b == 2
    assert removed_old.b == 2
    assert not hasattr(removed_new, "b")
