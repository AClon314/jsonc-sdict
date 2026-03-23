"""shared static public lib"""

from types import MappingProxyType

import os
import logging
from collections.abc import Callable, Iterable, Generator
from typing import cast, Any, ParamSpec, TypeIs, TypeVar, FrozenSet, overload


type RAISE = "RAISE"  # type:ignore
"""allow raise by default"""
type UNSET = "UNSET"  # type: ignore
"""do NOT use this arg, like undefined"""
type NONE = "NONE"  # type: ignore
"""gen.send(NONE) to give None as new value"""
Scalar = None | bool | int | float | str | bytes | bytearray
ImmutableContainers = tuple | MappingProxyType | FrozenSet

LOG = os.environ.get("LOG", "INFO").upper()
IS_DEBUG = LOG == "DEBUG" or os.environ.get("TERM_PROGRAM", None)
logging.basicConfig(format="%(levelname)s %(asctime)s %(name)s:%(lineno)d\t%(message)s")
if IS_DEBUG:
    LOG = "DEBUG"


def getLogger(name: str | None = None) -> logging.Logger:
    Log = logging.getLogger(__name__)
    Log.setLevel(LOG)
    return Log


def iterable[V](obj: Iterable[V] | Any) -> TypeIs[Iterable[V]]:
    """Iterable but NOT str, bytes"""
    return isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, bytearray))


def return_of[Y, S, R](gen: Generator[Y, S, R], send: S = None) -> R:
    """
    consume generator and get its return.

    Args:
        send: value sent after the first yield. `None` matches `for _ in gen`.

    Raises:
        GeneratorExit
        MemoryError
    """
    try:
        next(gen)
        while True:
            gen.send(send)
    except StopIteration as e:
        return e.value


@overload
def return_from[Y, S, R](gen: Generator[Y, S, R]) -> Generator[Y, S, R]: ...


@overload
def return_from[R](gen: R) -> Generator[None, None, R]: ...


def return_from[Y, S, R](gen: Generator[Y, S, R] | R) -> Generator[Y, S, R]:
    """usage: `yield from return_from(gen_or_func())`"""
    if isinstance(gen, Generator):
        ret: R = yield from gen
    else:
        ret = gen
    return ret


def yields_of[Y, S, R](gen: Generator[Y, S, R], send: S = None) -> tuple[list[Y], R]:
    """
    consume generator and get its yields.

    Args:
        send: to gen

    Returns:
        return, yields

    Raises:
        GeneratorExit
        MemoryError
    """
    yields: list[Y] = []
    try:
        v = next(gen)
        yields.append(v)
        while True:
            v = gen.send(send)
            yields.append(v)
    except StopIteration as e:
        return yields, e.value


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


def len_slice(len: int, Slice: slice) -> int:
    """
    计算对长度为 len 的序列应用指定切片后，得到的新序列的有效长度

    参数:
        len: int - 原序列的长度（必须非负）
        Slice: slice - 要应用的切片对象

    返回:
        int - 切片后的有效长度（非负）

    异常:
        ValueError - 当原长度为负数，或切片的 step 为 0 时抛出
    """
    # 校验原长度合法性
    if len < 0:
        raise ValueError("原序列长度不能为负数")

    # 处理空序列的特殊情况（直接返回0）
    if len == 0:
        return 0

    # 提取切片的start、stop、step，并处理默认值
    start = Slice.start
    stop = Slice.stop
    step = Slice.step if Slice.step is not None else 1

    # 校验step合法性（Python原生切片不允许step=0）
    if step == 0:
        raise ValueError("切片的步长(step)不能为0")

    # --------------------------
    # 第一步：处理start的有效索引
    # --------------------------
    if start is None:
        # step为正，start默认从0开始；step为负，start默认从最后一个元素(len-1)开始
        effective_start = 0 if step > 0 else len - 1
    else:
        # 转换负数索引为正数
        effective_start = start if start >= 0 else len + start
        # 处理超出范围的start：
        # - step为正，start < 0 则取0；start >= len 则取len
        # - step为负，start >= len 则取len-1；start < 0 则取-1（后续判断会直接返回0）
        if step > 0:
            effective_start = max(0, min(effective_start, len))
        else:
            effective_start = max(-1, min(effective_start, len - 1))

    # --------------------------
    # 第二步：处理stop的有效索引
    # --------------------------
    if stop is None:
        # step为正，stop默认到len；step为负，stop默认到-1（超出左边界）
        effective_stop = len if step > 0 else -1
    else:
        # 转换负数索引为正数
        effective_stop = stop if stop >= 0 else len + stop
        # 处理超出范围的stop：
        # - step为正，stop < 0 则取0；stop > len 则取len
        # - step为负，stop > len-1 则取len-1；stop < -1 则取-1
        if step > 0:
            effective_stop = max(0, min(effective_stop, len))
        else:
            effective_stop = max(-1, min(effective_stop, len - 1))

    # --------------------------
    # 第三步：计算有效长度
    # --------------------------
    if step > 0:
        # 步长为正：start >= stop 时，有效长度为0；否则计算 (stop - start) // step
        if effective_start >= effective_stop:
            return 0
        else:
            # 公式：元素个数 = ((结束索引 - 起始索引) + 步长 - 1) // 步长 （向上取整）
            return (effective_stop - effective_start + step - 1) // step
    else:
        # 步长为负：start <= stop 时，有效长度为0；否则计算 (start - stop) // abs(step)
        if effective_start <= effective_stop:
            return 0
        else:
            return (effective_start - effective_stop + abs(step) - 1) // abs(step)


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
