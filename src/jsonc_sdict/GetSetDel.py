"""for nested obj"""

from __future__ import annotations

from collections.abc import (
    Iterable,
    Sequence,
    Callable,
    Generator,
    MutableMapping,
    MutableSequence,
    MutableSet,
)
from typing import Any, TypedDict, cast

from jsonc_sdict.share import NONE, RAISE, iterable

_TYPE_Exceptions = tuple[type[BaseException], ...]


class gets[K, D]:
    """Walk a nested path and yield each visited object along the path."""

    ERROR_ATTR = (TypeError, AttributeError)
    ERROR_ITEM = (TypeError, KeyError, IndexError)
    ERROR_IA = (TypeError, KeyError, IndexError, AttributeError)

    @classmethod
    def getter(
        cls,
        get: Callable[[Any, K], Any],
        obj,
        keys: Iterable[K] | K,
        default: D | RAISE = RAISE,
        noRaise: _TYPE_Exceptions = ERROR_IA,
    ) -> Generator[Any | D]:
        if default is RAISE:
            noRaise = ()
        try:
            if not iterable(keys):
                yield get(obj, keys)  # type: ignore : compatible but not rigorous
                return
            if not keys:
                yield obj
                return
            for k in keys:
                obj = get(obj, k)
                yield obj
        except noRaise:
            return default

    @staticmethod
    def _get_item(obj, k):
        return obj[k]

    @classmethod
    def item(
        cls,
        obj,
        keys: Iterable[K] | K,
        default: D | RAISE = RAISE,
        noRaise: _TYPE_Exceptions = ERROR_ITEM,
    ) -> Generator[Any | D]:
        """Yield visited values for an item-only path like `obj[k0][k1]...`."""
        yield from cls.getter(
            get=cls._get_item,
            obj=obj,
            keys=keys,
            default=default,
            noRaise=noRaise,
        )

    @classmethod
    def attr(
        cls,
        obj,
        keys: Iterable[K] | K,
        default: D | RAISE = RAISE,
        noRaise: _TYPE_Exceptions = ERROR_ATTR,
    ) -> Generator[Any | D]:
        """Yield visited values for an attr-only path like `obj.a.b...`."""
        yield from cls.getter(
            get=getattr,
            obj=obj,
            keys=keys,
            default=default,
            noRaise=noRaise,
        )

    @staticmethod
    def _get_ia(obj, k):
        return obj[k] if hasattr(obj, "__getitem__") else getattr(obj, k)

    @classmethod
    def ia(
        cls,
        obj,
        keys: Iterable[K] | K,
        default: D | RAISE = RAISE,
        noRaise: _TYPE_Exceptions = ERROR_IA,
    ) -> Generator[Any | D]:
        """Yield visited values for a mixed item/attr path."""
        yield from cls.getter(
            get=cls._get_ia,
            obj=obj,
            keys=keys,
            default=default,
            noRaise=noRaise,
        )

    class Kwargs(TypedDict, total=False):
        obj: Any
        keys: Iterable[K] | K
        default: D | RAISE
        noRaise: _TYPE_Exceptions


class get1[K, D]:
    """Resolve a nested path and return the final target value."""

    @classmethod
    def getter(
        cls,
        get: Callable[[Any, K], Any],
        obj,
        keys: Iterable[K] | K,
        default: D | RAISE = RAISE,
        noRaise: _TYPE_Exceptions = gets.ERROR_IA,
    ) -> Any | D:
        if default is RAISE:
            noRaise = ()
        if not iterable(keys):
            return get(obj, keys)  # type: ignore : compatible but not rigorous
        if not keys:
            return obj
        try:
            for k in keys:
                obj = get(obj, k)
            return obj
        except noRaise:
            return default

    @classmethod
    def item(
        cls,
        obj,
        keys: Iterable[K] | K,
        default: D | RAISE = RAISE,
        noRaise: _TYPE_Exceptions = gets.ERROR_ITEM,
    ) -> Any | D:
        """
        Access a nested item path like `obj[k0][k1]...`.

        Args:
            obj: An object supporting nested `__getitem__()`.
            keys: A single key or key path.
            default: Fallback returned when an exception in `noRaise` is hit.
            noRaise: Exceptions to suppress. Use `()` to raise everything.
        """
        return cls.getter(
            get=gets._get_item,
            obj=obj,
            keys=keys,
            default=default,
            noRaise=noRaise,
        )

    @classmethod
    def attr(
        cls,
        obj,
        keys: Iterable[K] | K,
        default: D | RAISE = RAISE,
        noRaise: _TYPE_Exceptions = gets.ERROR_ATTR,
    ) -> Any | D:
        """
        Access a nested attr path like `obj.a.b...`.

        Args:
            obj: An object exposing nested attributes.
            keys: A single attr name or attr path.
            default: Fallback returned when an exception in `noRaise` is hit.
            noRaise: Exceptions to suppress. Use `()` to raise everything.
        """
        return cls.getter(
            get=getattr,
            obj=obj,
            keys=keys,
            default=default,
            noRaise=noRaise,
        )

    @classmethod
    def ia(
        cls,
        obj,
        keys: Iterable[K] | K,
        default: D | RAISE = RAISE,
        noRaise: _TYPE_Exceptions = gets.ERROR_IA,
    ) -> Any | D:
        """
        Access a mixed nested path, trying item access before attr access.

        Args:
            obj: An object supporting nested item and/or attr access.
            keys: A single key or key path.
            default: Fallback returned when an exception in `noRaise` is hit.
            noRaise: Exceptions to suppress. Use `()` to raise everything.
        """
        return cls.getter(
            get=gets._get_ia,
            obj=obj,
            keys=keys,
            default=default,
            noRaise=noRaise,
        )

    Kwargs = gets.Kwargs


_TYPE_MutMapSeq = MutableMapping | MutableSequence


class set1[OBJ, K]:
    """Write a nested path and return the previous leaf value if it existed."""

    _TYPE_PAVE = (
        Callable[[OBJ, Sequence[K]], Generator[_TYPE_MutMapSeq, K, Any]]
        | Callable[[OBJ, K], _TYPE_MutMapSeq]
    )

    @staticmethod
    def _set_root(obj, value) -> None:
        if hasattr(obj, "__setitem__"):
            obj.clear()
            if isinstance(obj, (MutableMapping, MutableSet)):
                obj.update(value)
            elif isinstance(obj, MutableSequence):
                obj.extend(value)
            else:
                raise TypeError(f"Failed to update {type(obj)=} at root level")
        else:
            obj.__dict__.clear()
            obj.__dict__.update(value.__dict__)

    @classmethod
    def setter(
        cls,
        get: Callable[[Any, K], Any],
        set: Callable[[Any, K, Any], Any],
        obj: OBJ,
        keys: Sequence[K] | K,
        value,
        pave: _TYPE_PAVE | None = None,
        noRaise: _TYPE_Exceptions = gets.ERROR_IA,
    ) -> Any | NONE:
        """
        Args:
            noRaise: do NOT raise when get() and `pave` is on, but we still raise Exception on set()
        """
        key: K | None
        if not iterable(keys):
            key = cast(K, keys)
        elif not keys:
            cls._set_root(obj, value)
            return NONE
        else:
            keys = cast(Sequence[K], keys)
            key = keys[0] if len(keys) == 1 else None

        if key is not None:
            old = NONE
            try:
                old = get(obj, key)
            except noRaise:
                pass
            set(obj, key, value)
            return old

        getter = None
        if pave:
            _gen = None
            try:
                _gen = pave(obj, keys)  # type: ignore : init gen
                if not isinstance(_gen, Generator):
                    raise TypeError(
                        "pave fallback to Callable[[OBJ, K], _TYPE_MutMapSeq]"
                    )

                _gen.send(None)

                def pave(obj, k) -> _TYPE_MutMapSeq:
                    return _gen.send(k)  # type: ignore
            except TypeError:  # positional arguments
                pass

            def getter(obj, k):
                try:
                    return get(obj, k)
                except noRaise:
                    return pave(obj, k)
                    # NOTE: more compability but with more debug hell:
                    # if (entry := pave(obj, k)) and entry is not None:
                    #     return entry
                    # return get(obj, k)

        iterate = gets.getter(
            get=getter if getter else get, obj=obj, keys=keys[:-1], noRaise=noRaise
        )

        objs = list(iterate)
        parent = objs[-1]
        lastKey = keys[-1]
        old = NONE
        try:
            old = get(parent, lastKey)
        except noRaise:
            pass
        set(parent, lastKey, value)
        return old

    @staticmethod
    def _set_item(obj, k, v):
        obj[k] = v

    @staticmethod
    def pave_dict(obj, k) -> _TYPE_MutMapSeq:
        """Create a missing dict node for `set1.item()` paving."""
        dic = {}
        obj[k] = dic  # NOTE: you need manually set(你要手动设置值)
        return dic

    @staticmethod
    def pave_dict_gen(obj, keys) -> Generator[_TYPE_MutMapSeq, K, Any]:
        new_k = yield
        for k in keys:
            assert new_k == k
            dic = {}
            obj[new_k] = dic
            new_k = yield dic

    @classmethod
    def item(
        cls,
        obj: OBJ,
        keys: Sequence[K] | K,
        value,
        pave: _TYPE_PAVE | None = None,
        noRaise: _TYPE_Exceptions = gets.ERROR_ITEM,
    ) -> Any | NONE:
        """
        Set an item-only path like `obj[k0][k1]... = value`.

        Args:
            pave: Optional path-paving callback for missing parents.
        """
        return cls.setter(
            get=gets._get_item,
            set=cls._set_item,
            obj=obj,
            keys=keys,
            value=value,
            pave=pave,
            noRaise=noRaise,
        )

    @staticmethod
    def _set_ia(obj, k, v):
        if hasattr(obj, "__setitem__"):
            obj[k] = v
        else:
            setattr(obj, k, v)

    @classmethod
    def ia(
        cls,
        obj: OBJ,
        keys: Sequence[K] | K,
        value,
        pave: _TYPE_PAVE | None = None,
        noRaise: _TYPE_Exceptions = gets.ERROR_IA,
    ) -> Any | NONE:
        """Set a mixed item/attr path and return the previous leaf value."""
        return cls.setter(
            get=gets._get_ia,
            set=cls._set_ia,
            obj=obj,
            keys=keys,
            value=value,
            pave=pave,
            noRaise=noRaise,
        )

    class Kwargs(TypedDict):
        pave: set1._TYPE_PAVE | None
        noRaise: _TYPE_Exceptions


class del1[OBJ, K]:
    """Delete a nested path."""

    @classmethod
    def deleter(
        cls,
        get: Callable[[Any, K], Any],
        delete: Callable[[Any, K], Any],
        obj: OBJ,
        keys: Sequence[K] | K,
        noRaise: _TYPE_Exceptions = gets.ERROR_IA,
    ) -> None:
        key: K | None
        if not iterable(keys):
            key = cast(K, keys)
        else:
            keys = cast(Sequence[K], keys)
            if not keys:
                raise ValueError(f"{keys=} is empty, {obj=}")
            key = keys[0] if len(keys) == 1 else None

        if key is not None:
            delete(obj, key)
            return

        parent = get1.getter(
            get=get,
            obj=obj,
            keys=keys[:-1],
            noRaise=noRaise,
        )
        delete(parent, keys[-1])

    @staticmethod
    def _del_item(obj, k):
        del obj[k]

    @staticmethod
    def _del_ia(obj, k):
        if hasattr(obj, "__delitem__"):
            del obj[k]
        else:
            delattr(obj, k)

    @classmethod
    def item(
        cls,
        obj: OBJ,
        keys: Sequence[K] | K,
        noRaise: _TYPE_Exceptions = gets.ERROR_ITEM,
    ) -> None:
        """Delete an item-only path like `del obj[k0][k1]...`."""
        return cls.deleter(
            get=gets._get_item,
            delete=cls._del_item,
            obj=obj,
            keys=keys,
            noRaise=noRaise,
        )

    @classmethod
    def ia(
        cls,
        obj: OBJ,
        keys: Sequence[K] | K,
        noRaise: _TYPE_Exceptions = gets.ERROR_IA,
    ) -> None:
        """Delete a mixed item/attr path."""
        return cls.deleter(
            get=gets._get_ia,
            delete=cls._del_ia,
            obj=obj,
            keys=keys,
            noRaise=noRaise,
        )
