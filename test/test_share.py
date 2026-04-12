from typing import Literal

import pytest

from jsonc_sdict.share import in_range, len_slice, return_of, args_of_type, yields_of


def test_return_helpers_consume_generators():
    def gen():
        first = yield "a"
        second = yield (first or "b")
        return second or "done"

    assert yields_of(gen()) == (["a", "b"], "done")
    assert return_of(gen()) == "done"


def test_return_helpers_do_not_swallow_inner_type_error():
    def gen():
        raise TypeError("inner boom")
        yield

    with pytest.raises(TypeError, match="inner boom"):
        return_of(gen())

    with pytest.raises(TypeError, match="inner boom"):
        yields_of(gen())


def test_in_range():
    assert in_range(2, slice(0, 5))
    assert not in_range(5, slice(0, 5))
    assert in_range(3, slice(1, None, 2))
    assert not in_range(4, slice(1, None, 2))
    assert in_range(4, slice(5, 0, -1))
    assert not in_range(0, slice(5, 0, -1))
    assert in_range(4, slice(-2, None), total=5)
    assert in_range(-1, slice(-2, None), total=5)
    assert not in_range(4, slice(None, -1), total=5)
    assert in_range(-1, slice(None, None, -1), total=5)


def test_len_slice():
    assert len_slice(10, slice(2, 8, 2)) == 3
    assert len_slice(5, slice(-3, 5)) == 3
    assert len_slice(10, slice(8, 2, -2)) == 3
    assert len_slice(5, slice(10, 20)) == 0
    assert len_slice(7, slice(None)) == 7
    assert len_slice(0, slice(1, 3)) == 0


def test_values_of_type_unwraps_nested_type_alias_union():
    type Base = Literal[1, 2]
    type Nested = Base | Literal[2, 3]
    type Wrapped = Nested | Base

    assert args_of_type(Wrapped) == (1, 2, 3)
