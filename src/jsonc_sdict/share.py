"""shared static public lib"""

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, cast


type RAISE = "❌"  # type:ignore
"""allow raise by default"""


def in_range(v: int, Slice: slice) -> bool:
    """v in_range of Slice?"""
    # 类型校验：确保v是整数
    if not isinstance(v, int):
        raise TypeError(f"{type(v)=},but should be int")

    # 提取切片的核心参数，设置默认值（匹配Python原生slice逻辑）
    start = Slice.start if Slice.start is not None else 0
    stop = Slice.stop
    step = Slice.step if Slice.step is not None else 1

    # 处理step=0的非法场景
    if step == 0:
        raise ValueError("slice step cannot be zero")

    # 无步长（step=1）的基础判断逻辑
    if step == 1:
        # 处理start边界：start为None/≤v 则满足
        start_ok = v >= start
        # 处理stop边界：stop为None 或 v < stop 则满足
        stop_ok = stop is None or v < stop
        return start_ok and stop_ok

    # 有步长的复杂判断逻辑（覆盖正负步长、stop=None场景）
    else:
        # 场景1：stop为None（无终止边界）
        if stop is None:
            # 正步长：v ≥ start 且 (v - start) 能被step整除 且 差值≥0
            if step > 0:
                return v >= start and (v - start) % step == 0 and (v - start) >= 0
            # 负步长：v ≤ start 且 (v - start) 能被step整除 且 差值≤0
            else:
                return v <= start and (v - start) % step == 0 and (v - start) <= 0

        # 场景2：stop不为None（有终止边界）
        else:
            # 正步长：start ≤ v < stop 且 (v - start) 能被step整除
            if step > 0:
                return start <= v < stop and (v - start) % step == 0
            # 负步长：stop < v ≤ start 且 (v - start) 能被step整除
            else:
                return stop < v <= start and (v - start) % step == 0


PS = ParamSpec("PS")
TV = TypeVar("TV")


def copy_args(
    func: Callable[PS, Any],
) -> Callable[[Callable[..., TV]], Callable[PS, TV]]:
    """Decorator does nothing but returning the casted original function"""

    def return_func(func: Callable[..., TV]) -> Callable[PS, TV]:
        return cast(Callable[PS, TV], func)

    return return_func


def check_hashWeak(obj: Any):
    try:
        hash(obj)
        # 检查__weakref__（存在弱引用支持）
        _ = obj.__weakref__
    except (TypeError, AttributeError) as e:
        raise TypeError(
            f"Inserted object {obj!r} must support __hash__ and __weakref__ "
            "(e.g. custom class instances, not dict/list/basic types like int/str)"
        ) from e


def test():
    # 测试无步长场景
    assert in_range(2, slice(0, 5)) == True
    assert in_range(5, slice(0, 5)) == False

    # 测试有步长+stop=None场景
    assert in_range(3, slice(1, None, 2)) == True  # 1,3,5...
    assert in_range(4, slice(1, None, 2)) == False

    # 测试负步长场景
    assert in_range(4, slice(5, 0, -1)) == True  # 5,4,3,2,1
    assert in_range(0, slice(5, 0, -1)) == False

    # 测试异常场景（验证报错）
    try:
        in_range(1, slice(0, 5, 0))
    except ValueError as e:
        assert str(e) == "slice step cannot be zero"


if __name__ == "__main__":
    test()
