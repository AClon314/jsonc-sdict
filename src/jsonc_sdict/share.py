"""shared static public lib"""

import os
import ast
import inspect
import logging
from argparse import ArgumentParser
from dataclasses import dataclass
from importlib import import_module
from itertools import islice
from collections.abc import (
    Callable,
    Iterable,
    Generator,
    Mapping,
    Collection,
    Iterator,
    Sized,
)
from pathlib import Path
from types import MappingProxyType
from typing import (
    get_args,
    overload,
    Any,
    Never,
    Union,
    TypeIs,
    TypeVar,
    FrozenSet,
    ParamSpec,
    TypeAliasType,
)


type RAISE = "RAISE"  # type:ignore
"""allow raise by default"""
type UNSET = "UNSET"  # type: ignore
"""do NOT use this arg, like undefined"""
type NONE = "NONE"  # type: ignore
"""gen.send(NONE) to give None as new value"""
Scalar = None | bool | int | float | str | bytes | bytearray
ImmutableContainers = tuple | MappingProxyType | FrozenSet
PS = ParamSpec("PS")

LOG = os.environ.get("LOG", "INFO").upper()
IS_DEBUG = LOG == "DEBUG" or os.environ.get("TERM_PROGRAM", None)
logging.basicConfig(format="%(levelname)s %(asctime)s %(name)s:%(lineno)d\t%(message)s")
if IS_DEBUG:
    LOG = "DEBUG"


_PKG_DIR = Path(__file__).resolve().parent
_PKG_ = __package__ or _PKG_DIR.stem
_TODO = NotImplementedError(
    "rare edge case, click https://github.com/AClon314/jsonc-sdict/issues to report"
)


def getLogger(name: str | None = None) -> logging.Logger:
    Log = logging.getLogger(__name__)
    Log.setLevel(LOG)
    return Log


Log = getLogger(__name__)


def iterable[V](obj: Iterable[V] | Any) -> TypeIs[Iterable[V]]:
    """Iterable but NOT str, bytes"""
    return isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, bytearray))


def isFlatIterable[V](obj: Iterable[V] | Any) -> TypeIs[Iterable[V]]:
    """[0,1,"s"] return True; [0, {...}, [...]] return False"""
    return iterable(obj) and not any(
        iterable(x) for x in (obj.values() if isinstance(obj, Mapping) else obj)
    )


def iSlice[T](iter: Sized[T], stop: int | None = -1) -> islice[T]:
    """by default remove the last one"""
    if stop is not None and stop < 0:
        stop = max(0, len(iter) + stop)
    return islice(iter, stop)


@overload
def unpack_method[T, R](
    deco: classmethod[T, PS, R], cls: type[T]
) -> Callable[PS, R]: ...


@overload
def unpack_method[R](deco: staticmethod[PS, R]) -> Callable[PS, R]: ...


@overload
def unpack_method[R](deco: Callable[PS, R]) -> Callable[PS, R]: ...


@overload
def unpack_method(deco: Any) -> Callable | None: ...


def unpack_method(
    deco: classmethod | staticmethod, cls: type | None = None
) -> Callable | None:
    """
    Returns
        None if deco is not Callable
    """
    if isinstance(deco, classmethod):
        return deco.__get__(None, cls)
    elif isinstance(deco, staticmethod):
        return deco.__get__(None, None)
    elif isinstance(deco, Callable):
        return deco
    return None


def return_of[Y, S, R](gen: Generator[Y, S, R] | Iterator[Y], send: S = None) -> R:
    """
    consume generator and get its return.

    Args:
        send: value sent after the first yield. `None` matches `for _ in gen`.

    Raises:
        GeneratorExit
        MemoryError
    """
    isGen = isinstance(gen, Generator)
    try:
        if not isGen or inspect.getgeneratorstate(gen) == inspect.GEN_CREATED:
            next(gen)
        else:
            gen.send(send)
        while True:
            gen.send(send) if isGen else next(gen)
    except StopIteration as e:
        return e.value


@overload
def return_from[Y, S, R](gen: Generator[Y, S, R]) -> Generator[Y, S, R]: ...


@overload
def return_from[Y](gen: Iterator[Y]) -> Generator[Y, Never, None]: ...


@overload
def return_from[R](gen: R) -> Generator[None, None, R]: ...


def return_from[Y, S, R = None](
    gen: Generator[Y, S, R] | Iterator[Y] | R,
) -> Generator[Y, S, R]:
    """usage: `yield from return_from(gen_or_func())`"""
    if isinstance(gen, (Generator, Iterator)):
        ret: R = yield from gen
    else:
        ret = gen
    return ret


def in_range(i: int, Slice: slice, total: int | None = None) -> bool:
    """i in_range of Slice.
    Args:
        total: \\>=0. Set this as `i`'s max/len, if you want [:-1] negative index support.
    """
    assert isinstance(i, int), f"{type(i)=},but should be int"
    assert total is None or total >= 0, f"{total=} should >= 0"
    step = Slice.step if Slice.step is not None else 1
    if step == 0:
        raise ValueError("slice step cannot be zero")

    if total is not None:
        if i < 0:
            i += total
        if not 0 <= i < total:
            return False
        return i in range(*Slice.indices(total))

    start = Slice.start if Slice.start is not None else (0 if step > 0 else -1)
    stop = Slice.stop

    if stop is None:
        if step > 0:
            return i >= start and (i - start) % step == 0
        return i <= start and (i - start) % step == 0

    if step > 0:
        return start <= i < stop and (i - start) % step == 0
    return stop < i <= start and (i - start) % step == 0


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


def are_equal(
    a,
    b,
    preprocess: Callable[[Any], Any] | None = None,
    _seen: set[tuple[int, int]] | None = None,
):
    """also compare the **order of keys**, because python's `==` will ignore that"""
    if id(a) == id(b):
        return True
    if preprocess:
        a = preprocess(a)
        b = preprocess(b)
    if id(a) == id(b):
        return True

    # `seen` to avoid RecursionError
    # a = {}
    # a["self"] = a
    if _seen is None:
        _seen = set()
    pair = (id(a), id(b))
    if pair in _seen:
        return True
    _seen.add(pair)

    if isinstance(a, Mapping) and isinstance(b, Mapping):
        if len(a) != len(b):
            return False
        for (ka, va), (kb, vb) in zip(a.items(), b.items(), strict=True):
            if ka != kb:
                return False
            if not are_equal(va, vb, preprocess, _seen):
                return False
        return True

    if iterable(a) and iterable(b):
        if isinstance(a, Collection) and isinstance(b, Collection) and len(a) != len(b):
            return False
        return all(
            are_equal(x, y, preprocess, _seen) for x, y in zip(a, b, strict=True)
        )

    return a == b


def text_from_shell(path_or_str: str) -> str:
    p = Path(path_or_str)
    return p.read_text(encoding="utf-8") if p.exists() else path_or_str


def typeof[T](alias: T) -> T:
    while type(alias) is TypeAliasType:
        alias = alias.__value__
    return alias


def unpack_type[T](typ: T) -> Generator[T, Never, None]:
    typ = typeof(typ)
    if type(typ) is Union:
        for member in get_args(typ):
            yield from unpack_type(member)
        return
    yield from get_args(typ)


def args_of_type[T](typ: T) -> tuple[T, ...]:
    return tuple(dict.fromkeys(unpack_type(typ)))


@dataclass
class ModVars:
    Class: list[str]
    Func: list[str]
    Else: list[str]


def vars_of(path: Path, pkg: str = _PKG_) -> ModVars:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    Class = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    Func = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    parts = path.parent.parts + (path.stem,)
    mod_name = ".".join(parts[parts.index(pkg) :])
    mod = import_module(mod_name, pkg)
    Else = list(
        {v for v in vars(mod).keys() if not v.startswith("_")} - set(Class) - set(Func)
    )
    return ModVars(Class=Class, Func=Func, Else=Else)


def mods_of(path: Path = _PKG_DIR) -> dict[str, ModVars]:
    return {p.stem: vars_of(p) for p in sorted(path.glob("*.py"))}


def Help(Else=False) -> str:
    """list all useable funcs"""
    out = ""
    for mod, var in mods_of().items():
        from_import = f"from {_PKG_}.{mod} import \t"
        if var.Class:
            out += "\n# 📚 class\n" + from_import + ", ".join(var.Class)
        if var.Func:
            out += "\n# func\n" + from_import + ", ".join(var.Func)
        if Else and var.Else:
            out += "\n# else\n" + from_import + ", ".join(var.Else)
        out += "\n"
    return out.strip()


def try_autocomplete(parser: ArgumentParser):
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError as e:
        Log.warning("skip argcomplete", exc_info=e)


PS = ParamSpec("PS")
TV = TypeVar("TV")


def copy_args(
    func: Callable[PS, Any],
) -> Callable[[Callable[..., TV]], Callable[PS, TV]]:
    """Decorator does nothing but returning the casted original function"""

    def return_func(func: Callable[..., TV]) -> Callable[..., TV]:
        return func

    return return_func
