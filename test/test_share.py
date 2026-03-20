from jsonc_sdict.share import in_range, len_slice, return_of, yields_of


def test_return_helpers_consume_generators():
    def gen():
        first = yield "a"
        second = yield (first or "b")
        return second or "done"

    assert yields_of(gen()) == (["a", "b"], "done")
    assert return_of(gen()) == "done"


def test_in_range():
    assert in_range(2, slice(0, 5))
    assert not in_range(5, slice(0, 5))
    assert in_range(3, slice(1, None, 2))
    assert not in_range(4, slice(1, None, 2))
    assert in_range(4, slice(5, 0, -1))
    assert not in_range(0, slice(5, 0, -1))


def test_len_slice():
    assert len_slice(10, slice(2, 8, 2)) == 3
    assert len_slice(5, slice(-3, 5)) == 3
    assert len_slice(10, slice(8, 2, -2)) == 3
    assert len_slice(5, slice(10, 20)) == 0
    assert len_slice(7, slice(None)) == 7
    assert len_slice(0, slice(1, 3)) == 0
