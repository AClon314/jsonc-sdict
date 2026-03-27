from jsonc_sdict.sdict import sdict
import pytest

from jsonc_sdict.merge import DeepDiffProtocol, merge
from jsonc_sdict.share import return_of


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

    merged = return_of(merge((t1, t2), dictDict=None))
    should = {
        "list-no^": [1, 2, 3, 4],
        "list^": [1, 2, 3],
        "dict^": {"dict-no^": {0: 1, 1: 2}, "^": 0},
        "dict-easy": {0: 0, 1: 1},
    }
    assert sdict.are_equal(merged, should)
