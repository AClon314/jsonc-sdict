"""Shared sentinels, typing helpers, logging, and small utility functions."""

from __future__ import annotations
import re
import os
import ast
import inspect
import logging
from uuid import uuid4
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
from types import MappingProxyType, UnionType
from typing import (
    Protocol,
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
    get_origin,
)


def _unpack_alias[T](typ: T) -> T:
    while type(typ) is TypeAliasType:
        typ = typ.__value__
    return typ


def _unpack_type[T](typ: T) -> Generator[T, Never, None]:
    typ = _unpack_alias(typ)
    if get_origin(typ) in (Union, UnionType):
        for member in get_args(typ):
            yield from _unpack_type(member)
        return
    args = get_args(typ)
    if args:
        yield from args
        return
    yield typ


def args_of_type[T](typ: T) -> tuple[T, ...]:
    return tuple(dict.fromkeys(_unpack_type(typ)))


type RAISE = "RAISE"  # type: ignore
"""allow raise by default"""
type UNSET = "UNSET"  # type: ignore
"""do NOT use this arg, like undefined"""
type NONE = "NONE"  # type: ignore
"""gen.send(NONE) to give None as new value"""
Scalar = None | bool | int | float | complex | str | bytes
"""yaml support byte by `!!binary |\\n`, json do NOT support complex,bytes"""
ImmutableContainers = tuple | MappingProxyType | FrozenSet
PS = ParamSpec("PS")

LOG = os.environ.get("LOG", "INFO").upper()
# NOTE: vscode will setup $TERM_PROGRAM in env
IS_DEBUG = LOG == "DEBUG" or os.environ.get("TERM_PROGRAM", None)
logging.basicConfig(format="%(levelname)s %(asctime)s %(name)s:%(lineno)d\t%(message)s")
if IS_DEBUG:
    LOG = "DEBUG"

SEED = uuid4()
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
    if (
        Slice.start is None
        and Slice.stop is None
        and (Slice.step is None or Slice.step == 1)
    ):
        return True
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


PS = ParamSpec("PS")
TV = TypeVar("TV")


def copy_args(
    func: Callable[PS, Any],
) -> Callable[[Callable[..., TV]], Callable[PS, TV]]:
    """Decorator does nothing but returning the casted original function. `pylance` OK but `ty` not working."""

    def return_func(func: Callable[..., TV]) -> Callable[..., TV]:
        return func

    return return_func


class RegexPattern[S: (str, bytes)](Protocol):
    """
    `re.Pattern` and `regex.Pattern` shared property subset.

    Keep this protocol on the common denominator:
    - keep stdlib-style positional parameters
    - exclude `regex`-only features like `named_lists`, `splititer`, `scanner`
    - exclude callback replacements to avoid coupling to a concrete `Match` type
    """

    def findall(self, *args, **kw) -> list[S]: ...
    def finditer(self, *args, **kw) -> Iterator: ...
    @property
    def flags(self) -> int: ...
    def fullmatch(self, *args, **kw) -> re.Match | None: ...
    @property
    def groupindex(self) -> Mapping[str, int]: ...
    @property
    def groups(self) -> int: ...
    def match(self, *args, **kw) -> re.Match | None: ...
    @property
    def pattern(self) -> S: ...
    def search(self, *args, **kw) -> re.Match | None: ...
    def split(self, *args, **kw) -> list[S]: ...
    def sub(self, *args, **kw) -> S: ...
    def subn(self, *args, **kw) -> tuple[S, int]: ...
