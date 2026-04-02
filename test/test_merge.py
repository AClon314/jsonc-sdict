import pytest

from jsonc_sdict.merge import DeepDiffProtocol, merge
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
        merge((t1, t2), dictDict={"idKey": "id"}, sameKey_diffValue="new")
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
