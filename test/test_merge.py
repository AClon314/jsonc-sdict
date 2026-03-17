from jsonc_sdict import merge, return_of
from jsonc_sdict.share import getLogger

Log = getLogger(__name__)


def test_merge():
    t1 = {"list-no^": [1, 2], "list^": [1, 2], "dict^": {"dict-no^": {0: 1}, "^": 0}}
    t2 = {"list-no^": [3, 4], "list^": [1, 3], "dict^": {"^": 0, "dict-no^": {1: 2}}}
    for d in (gen := merge((t1, t2))):
        Log.debug(d)
    merged, _ = return_of(gen)
    assert merged == {
        "list-no^": [1, 2, 3, 4],
        "list^": [1, 2, 3],
        "dict^": {"^": 0, "dict-no^": {0: 1, 1: 2}},
    }
