import pytest

from jsonc_sdict.merge import DeepDiffProtocol, merge
from jsonc_sdict.share import return_of


def test_merge_module_helpers_import_cleanly():
    assert issubclass(DeepDiffProtocol, object)
    assert getattr(DeepDiffProtocol, "_is_protocol", False) is True
    assert callable(merge.get_item)


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason="merge core flow is still draft and fails inside dictDict()",
)
def test_merge_runtime_is_not_ready():
    t1 = {"list-no^": [1, 2], "list^": [1, 2], "dict^": {"dict-no^": {0: 1}, "^": 0}}
    t2 = {"list-no^": [3, 4], "list^": [1, 3], "dict^": {"^": 0, "dict-no^": {1: 2}}}

    merged, _ = return_of(merge((t1, t2)))
    assert merged == {
        "list-no^": [1, 2, 3, 4],
        "list^": [1, 2, 3],
        "dict^": {"^": 0, "dict-no^": {0: 1, 1: 2}},
    }
