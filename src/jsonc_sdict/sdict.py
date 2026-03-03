"""
- Life cycle: long-lived
"""

import re
import itertools
from weakref import ref
from collections import OrderedDict
from functools import cached_property, partial
from typing import Any, Self, cast, Literal, overload
from collections.abc import (
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    Generator,
    Sequence,
)

from deepdiff import DeepDiff
from deepdiff.path import parse_path

from jsonc_sdict.share import UNSET, NONE, copy_args, iterable, in_range, getLogger
from jsonc_sdict.weakList import WeakList

type Key[K = Any, V = sdict] = K | int
"""sdict[ dict:Key | list:int-index ]"""
type KeyPaths[K = Any, V = Any] = tuple[list[Key[K, V]], ...]
"""[[parent1, parent2(depth==0)], [me,(depth==1)], [child1, child2, (depth==3) ...]]"""
type PathCount = tuple[int, ...]
type Node[K = int, V = Any] = Mapping[K, V] | Iterable[V]


type NestDict[K = str, Leaf = Any] = "dict[K, NestDict[K, Leaf] | Leaf]"
type NestJDict[K = str, Leaf = Any] = "sdict[K, NestJDict[K, Leaf] | Leaf]"
type NestMap[K = str, Leaf = Any] = "Mapping[K, NestMap[K, Leaf] | Leaf]"
type NestMutMap[K = str, Leaf = Any] = "MutableMapping[K, NestMutMap[K, Leaf] | Leaf]"
type NestDictList[K = str, Leaf = Any] = (
    "dict[K, list[NestDictList[K, Leaf]] | list[Leaf]]"
)
type NestMapIter[K = str, Leaf = Any] = (
    "Mapping[K, Iterable[NestMapIter[K, Leaf]] | Iterable[Leaf]]"
)

Log = getLogger(__name__)


def get_item[K, D](
    obj: NestMutMap[K],
    keys: Iterable[K],
    default: D = None,
    noRaise: tuple[type[BaseException], ...] = (KeyError, IndexError, TypeError),
) -> Any | D:
    """
    access nested obj like `obj[key0][key1]...`\n
    Args:
        obj: has nested `__getitem__()`, or raise `TypeError`
        keys: [key0, key1...], can raise `KeyError`(dict/map) or `IndexError`(list)
        default: when raise `Except`, return default as fallback
        noRaise: do NOT raise Error that in noRaise,\n
            can use `(Exception,)` to suppress all Exceptions,\n
            or use `()` to raise all Exceptions
    """
    if not iterable(keys):
        return obj[keys]
    try:
        for k in keys:
            obj = obj[k]
        return obj
    except noRaise:
        return default
    except Exception:
        raise


def get_attr[D](
    obj,
    keys: Iterable[str],
    default: D = None,
    noRaise: tuple[type[BaseException], ...] = (AttributeError,),
) -> Any | D:
    """
    access nested obj like `obj.key0.key1...`\n
    Args:
        obj: has nested attribute that link to deeper obj
        keys: [key0, key1...], can raise `AttributeError`
        default: when raise `Except`, return default as fallback
        noRaise: do NOT raise Error that in noRaise,\n
            can use `(Exception,)` to suppress all Exceptions,\n
            or use `()` to raise all Exceptions
    """
    if not iterable(keys):
        return getattr(obj, keys)
    try:
        for k in keys:
            obj = getattr(obj, k)
        return obj
    except noRaise:
        return default
    except Exception:
        raise


def get_item_attr[D](
    obj,
    keys: Iterable,
    default: D = None,
    noRaise: tuple[type[BaseException], ...] = (
        KeyError,
        IndexError,
        TypeError,
        AttributeError,
    ),
) -> Any | D:
    """
    **smartly** access nested obj like `obj[key0].key1...`\n
    try __getitem__() if has this method, or __getattribute__(), try like this in each level.\n
    Args:
        obj: need nested `__getitem__()` or `__getattribute__()` and implemented correctly
        keys: [key0, key1...]
        default: when raise `Except`, return default as fallback
        noRaise: do NOT raise Error that in noRaise,\n
            can use `(Exception,)` to suppress all Exceptions,\n
            or use `()` to raise all Exceptions
    """
    if not iterable(keys):
        if hasattr(obj, "__getitem__"):
            return obj[keys]
        else:
            return getattr(obj, keys)
    try:
        for k in keys:
            if hasattr(obj, "__getitem__"):
                obj = obj[k]
            else:
                obj = getattr(obj, k)
        return obj
    except noRaise:
        return default
    except Exception:
        raise


def set_item_attr(obj, keys: Sequence, value) -> None:
    """
    **smartly** access nested obj like `obj[key0].key1...`\n
    try __getitem__() if has this method, or __getattribute__(), try like this in each level.\n
    Args:
        obj: need nested `__get/setitem__()` or `__get/setattribute__()` and implemented correctly
        keys: [key0, key1...]
    """
    if not iterable(keys):
        if hasattr(obj, "__setitem__"):
            obj[keys] = value
        else:
            setattr(obj, keys, value)
        return
    parent = get_item_attr(obj, keys[:-1], noRaise=())
    k = keys[-1]
    if hasattr(obj, "__setitem__"):
        parent[k] = value
    else:
        setattr(parent, k, value)


def set_item(obj, keys: Sequence, value) -> None:
    """
    access nested obj like `obj[key0].key1...`\n
    try __getitem__() if has this method, or __getattribute__(), try like this in each level.\n
    Args:
        obj: need nested `__getitem__()` or `__getattribute__()` and implemented correctly
        keys: [key0, key1...]
    """
    parent = get_item_attr(obj, keys[:-1], noRaise=())
    k = keys[-1]
    parent[k] = value


def get_children[K, V](
    self: "sdict[K, V]", raw: Node[K, V] | Any, digList=True
):  # -> Generator[Iterable[K,V], None, None] | Generator[Iterable[tuple[int, V]], None, None]:
    """
    default getChild func
    Args:
        self: sdict that holding raw in `dfs()`
        raw: original data
            - dict: {key: value}
            - list: {index: value}
            - pydantic, dataclass...: visit `__dict__` to get {k:v}
        digList: set False if you want to stop before dig into list, only dict-dict-dict...
    """
    children = ()
    if isinstance(raw, Mapping):
        children = raw.items()
    elif hasattr(raw, "__dict__"):
        # pydantic / dataclass
        children = raw.__dict__.items()
    elif digList:
        # list
        children = enumerate(raw)
    return children


get_children_noList = partial(get_children, digList=False)
"""get_children(..., digList=False)"""

type YieldIfFunc[K, V] = Callable[[sdict[K, V], Node[K, V]], bool]

type GetChildFunc[K, V] = Callable[
    [sdict[K, V], Node[K, V]], Generator[Iterable[V], None, None] | Iterable[V]
]


def dfs[K = int, V = Any, KP = str](
    obj: Node[K, V],
    maxDepth=float("inf"),
    yieldIf: YieldIfFunc | None = None,
    getChild: GetChildFunc = get_children,
    readonly=False,
    *,
    parent: WeakList["sdict"] = WeakList(),
    keypath: KeyPaths = (),
    pathCount: PathCount = (0,),
):
    """
    do NOT update scaned/yielded data while iterating.
    Args:
        maxDepth: stop digging if deeper
        yieldIf: yield only if yield_if(self, node) is True
        getChild: see `get_children()`
    Usage:
    ```python
    for v in dfs(myDict):
        ...

    # if you offen dfs the same dict-object twice or even more, use cache:
    from jsonc_sdict import dfs, copy_args
    dfs_cache = lru_cache(maxsize=4096)(dfs)
    # if you like some type hint:
    # dfs_cache = copy_args(dfs)(lru_cache(maxsize=4096)(dfs))
    for v in dfs_cache(myDict):
        ...
    ```
    """
    # print(f"{type(obj)=}")
    if not iterable(obj) or len(keypath) > maxDepth:
        return obj

    pathCount = (*pathCount[:-1], pathCount[-1] + 1)
    if isinstance(obj, sdict) and not readonly:
        # update
        obj.parent = parent
        obj.keypath = keypath
        obj.pathCount = pathCount
        self = obj
    else:
        data = None
        ref = None
        if isinstance(obj, Mapping):
            data = obj
        else:
            # list / pydantic
            ref = obj
        self = sdict(
            data=data,
            ref=ref,
            # deep==True等价于执行dfs()，所以False即可
            deep=False,
            parent=parent,
            keypath=keypath,
            pathCount=pathCount,
        )
    newSelf = None
    if yieldIf is None or yieldIf(self, obj):
        newSelf = yield self
    if newSelf is not None:
        if newSelf is NONE:
            newSelf = None
        self = cast(sdict, self)
        # TODO: make sure parent[-1] always latest parent
        if self.parent:
            parent = self.parent[-1]
            lastKey = keypath[-1][-1]
            parent[lastKey] = newSelf  # TODO: need test
    children = getChild(self, obj)
    for i, (k, v) in enumerate(children):
        if not iterable(v):
            continue
        _parent = WeakList((self,))
        _keypath = (*keypath, [k])
        _pathCount = (*pathCount, i)
        ret = yield from dfs(
            v,
            maxDepth=maxDepth,
            yieldIf=yieldIf,
            getChild=getChild,
            readonly=readonly,
            parent=_parent,
            keypath=_keypath,
            pathCount=_pathCount,
        )
        if not readonly:
            # substitute python dict to sdict
            self[k] = ret
    return self


class sdict[K = str, V = Any, R = Any, KP = Any](OrderedDict[K, V]):
    """
    search-friendly dict, or "dict design for json in actual business", like benedict, but less limitation, more useful context, more strict type hint.

    Generic 泛型:
        K,V: the current depth that Key,Value's type \n
            当前层级的 Key, Value 键值类型
        R: type of self.ref
        KP: Type possibilities for all nested depths\n
            所有嵌套层的类型可能性
    """

    type IterAsMap = Iterable[tuple[K, V]] | Iterable[Iterable[K | V]]

    @property
    def v(self):
        """
        return self.ref if self is empty and ref is set else self\n
        will unpack weakref.ref
        """
        if not self.use_ref:
            return self
        elif isinstance(self.ref, ref):
            return self.ref()
        return self.ref

    def __init__(
        self,
        data: Mapping[K, V] | IterAsMap | None = None,
        ref: R | None = None,
        *,
        deep=True,
        parent: WeakList["sdict"] = WeakList(),
        keypath: KeyPaths[KP, "sdict"] = (),
        pathCount: PathCount = (0,),
        getChild: GetChildFunc = get_children,
    ):
        """
        Args:
            data: init dictionary, which unpack and create **shallow** copy (👍recommended, full-feature)
            ref: +1 reference\n
                `sdict(ref=myPydanticModel)` # keep `myPydanticModel` instance's orginal methods\n
                `s=sdict(ref=ref(hashableObj)); s.ref()` # return **None** after `del hashableObj`\n
                `s=sdict(ref=proxy(hashableObj)); s.ref` # raise **ReferenceError** after `del hashableObj`
            deep: exec `dfs()`/`sdict.rebuild()`, create **deep** copy, slower when init
            parent: weakref of parent
            getChild: used for __getitem__
        """
        self.repr = False
        """if you want `{}`, set to False; if you want `sdict({})` truly raw data, set to True"""
        self.use_ref = data is None
        """affect the return of self.v"""
        super().__init__(data or ())
        self.ref = ref
        """can storage pydantic_model_data, list_data..."""
        self.parent = parent
        self.keypath = keypath
        self.pathCount = pathCount
        if deep:
            self.rebuild()

    def rebuild(self):
        """build index/cache entirely.\n
        currently I recommand re-init a sdict instance if you want to **treat a child as new root node**, by `sdict(myChild_as_NewRoot_oldSdict)`
        """
        for _ in dfs(
            self,
            parent=self.parent,
            keypath=self.keypath,
            pathCount=self.pathCount,
        ):
            pass
        self.del_cache()

    def del_cache(self):
        try:
            del self.height
        except AttributeError as e:
            pass
            # Log.warning(e)
        try:
            del self.childkeys
        except AttributeError as e:
            pass
            # Log.warning(e)

    def getitem(
        self,
        key: Iterable[K],
        default=None,
        noRaise: tuple[type[BaseException], ...] = (
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
        ),
    ):
        """see `get_item_attr()`"""
        return get_item_attr(self.v, key, default, noRaise)

    def __getitem__(self, key: K | Iterable[K] | slice[int | None] | Any):
        if isinstance(key, slice):
            return [
                (
                    x
                    if isinstance(x, self.__class__)
                    else (
                        self.__class__(x, deep=False)
                        if isinstance(x, Mapping)
                        else self.__class__(ref=x, deep=False)
                        if iterable(x)
                        else x
                    )
                )
                for x in self.values_flat(slice=key)
            ]
        elif self.use_ref or iterable(key) and not isinstance(key, Mapping):
            # list / tuple
            v = self.getitem(key, noRaise=())
        else:
            # key = cast(K, key)
            v = super().__getitem__(key)

        if isinstance(v, self.__class__):
            return v
        return (
            self.__class__(v, deep=False)
            if isinstance(v, Mapping)
            else self.__class__(ref=v, deep=False)
            if iterable(v)
            else v
        )

    def setitem(self, key: Sequence[K], value, at=UNSET):
        """see `set_item_attr()`"""
        return set_item_attr(self.v if at is UNSET else at, key, value)

    def __setitem__(self, key: K | Sequence[K] | slice[int | None] | Any, value):
        if isinstance(key, slice):
            raise NotImplementedError("TODO")  # TODO: batch
            for i in self.keys_flat(slice=key):
                self[i] = value
        elif (
            self.use_ref
            or isinstance(key, Sequence)
            and not isinstance(key, (str, bytes, bytearray))
        ):
            self.setitem(key, value)
        else:
            super().__setitem__(key, value)
        self.del_cache()

    def __hash__(self):
        return id(self)

    # def __eq__(self, value: object) -> bool:
    #     if isinstance(value, self.__class__):
    #         return self.v == value.v
    #     return self.v == value

    def __repr__(self) -> str:
        r = super().__repr__()
        return r if self.repr else r[len(self.__class__.__name__) + 1 : -1] or "{}"

    @copy_args(OrderedDict.__ior__)
    def __ior__(self, value):
        if not value:
            return self
        super().__ior__(value)
        self.del_cache()
        return self

    @copy_args(OrderedDict.__delitem__)
    def __delitem__(self, key):
        super().__delitem__(key)
        self.del_cache()

    @copy_args(OrderedDict.pop)
    def pop(self, key):
        super().pop(key)
        self.del_cache()

    @copy_args(OrderedDict.popitem)
    def popitem(self, last):
        super().popitem(last)
        self.del_cache()

    @copy_args(OrderedDict.update)
    def update(self, m):
        if not m:
            return
        super().update(m)
        self.del_cache()

    @copy_args(OrderedDict.clear)
    def clear(self):
        super().clear()
        self.del_cache()

    # TODO: move_to_end, 暂时不做

    def rename_key(
        self,
        old: K | UNSET = UNSET,
        new: K | UNSET = UNSET,
        order: bool = True,
        deep: bool = False,
        can_rename: Callable[[MutableMapping[Any, Any]], bool] | None = None,
    ) -> Self:
        """
        Args:
            new: if `old` is `UNSET`, and `new` is set, will change `self`'s keyname at `self.parent[-1]`
            order: if you don't care about the order, set to `False`, it will be faster
            deep: if True, will deep rename. if False and old_key not in self, will **raise KeyError**
            can_rename: callback guard. return False to skip this parent
        """

        if new is UNSET:
            if old is UNSET:
                raise ValueError("old or new must be set")
            new = old
            old = UNSET
        elif old not in self and new in self:
            old, new = new, old

        def _rename_one(parent: MutableMapping, old_key: K, new_key: K):
            if old_key not in parent:
                return False
            if old_key == new_key:
                return True
            if not order:
                old_value = parent[old_key]
                del parent[old_key]
                parent[new_key] = old_value
                return True

            if isinstance(parent, self.__class__):
                parent.insert({new_key: parent[old_key]}, key=old_key)
                del parent[old_key]
                return True

            old_value = parent[old_key]
            ordered_items = []
            renamed = False
            for k, v in parent.items():
                if not renamed and k == old_key:
                    ordered_items.append((new_key, old_value))
                    renamed = True
                elif k == new_key:
                    continue
                else:
                    ordered_items.append((k, v))
            parent.clear()
            parent.update(ordered_items)
            return True

        def _can_rename(parent: MutableMapping[Any, Any]):
            if can_rename is None:
                return True
            return can_rename(parent)

        changed = False
        if old is UNSET:
            if not self.parent or not self.keypath:
                raise KeyError(new, "not found")
            parent = self.parent[-1]
            old = self.keypath[-1][-1]
            if not isinstance(parent, MutableMapping):
                raise TypeError(f"parent must be MutableMapping, got {type(parent)!r}")
            if old not in parent:
                raise KeyError(old, "not found")
            if _can_rename(parent):
                changed = _rename_one(parent, old, new)
            if changed:
                self.del_cache()
            return self

        if not deep:
            if old not in self:
                raise KeyError(old, "not found")
            if _can_rename(self):
                changed = _rename_one(self, old, new)
            if changed:
                self.del_cache()
            return self

        for parent in self.dfs(yieldIf=lambda parent, _: old in parent):
            if not _can_rename(parent):
                continue
            changed = _rename_one(parent, old, new) or changed
        if changed:
            self.del_cache()
        return self

    def rename_key_re(
        self,
        old: str | re.Pattern,
        new: str | re.Pattern,
        order: bool = True,
        deep: bool = False,
        can_rename: Callable[[MutableMapping[Any, Any]], bool] | None = None,
    ) -> Self:
        """
        regex version of `rename_key()`
        Args:
            can_rename: callback guard. return False to skip this parent
        """
        old_re = re.compile(old) if isinstance(old, str) else old
        if isinstance(new, str):
            try:
                new_re = re.compile(new)
            except re.error:
                # Replacement template may contain backrefs like `\1`.
                # Keep it compilable as Pattern while preserving replacement semantics.
                new_re = re.compile(re.escape(new))
            repl = new
        else:
            new_re = new
            repl = new_re.pattern

        def _rename_plan(parent: MutableMapping[Any, Any]) -> list[tuple[str, str]]:
            plan: list[tuple[str, str]] = []
            for key in parent.keys():
                if not isinstance(key, str) or old_re.search(key) is None:
                    continue
                new_name = old_re.sub(repl, key)
                if new_name == key:
                    continue
                plan.append((key, new_name))
            return plan

        def _rename_parent(parent: MutableMapping[Any, Any]) -> bool:
            if can_rename is not None and not can_rename(parent):
                return False
            plan = _rename_plan(parent)
            changed = False
            for old_name, new_name in plan:
                if old_name in parent:
                    parent.rename_key(old_name, new_name, order=order, deep=False)
                    changed = True
            return changed

        changed = False
        if not deep:
            if not _rename_plan(self):
                raise KeyError(old, "not found")
            changed = _rename_parent(self)
            if changed:
                self.del_cache()
            return self

        for parent in self.dfs(yieldIf=lambda parent, _: bool(_rename_plan(parent))):
            changed = _rename_parent(parent) or changed
        if changed:
            self.del_cache()
        return self

    @overload
    def merge(
        self,
        new: Mapping | DeepDiff,
        conflict=None,
        order: Literal["old", "new"] | None = "old",
    ) -> Generator[tuple[Any, Any, MutableMapping[Any, Any], Any], Any, Self]: ...

    @overload
    def merge(
        self,
        new: Mapping | DeepDiff,
        conflict: Literal["old", "new"],
        order: Literal["old", "new"] | None = "old",
    ) -> Self: ...

    def merge(
        self,
        new: Mapping | DeepDiff,
        conflict: Literal["old", "new"] | None = None,
        order: Literal["old", "new"] | None = "old",
    ) -> Self | Generator[tuple[Any, Any, MutableMapping[Any, Any], Any], Any, Self]:
        """
        if new is Map, will auto convert to DeepDiff in inner.
        *inspired by [deepmerge](https://github.com/toumorokoshi/deepmerge) & [deepdiff](https://github.com/seperman/deepdiff)*
        ```python
        for old_v, new_v, parent, key in (gen := jc.merge(new)):
            gen.send(NEW_V)
        ```

        Args:
            conflict: if None, will yield, and you can manually edit `parent[key] = ...`, or `gen.send(New_value) or gen.send(NONE)`
                if "old", will keep original value
                if "new", will override New's value
            order: if set "old", return merged dict in old dict order (respect user's order) \n
                set to "new" (force program order) \n
                if set None, will skip re-order, maybe faster.

        ## Yields
            old_v: old value
            new_v: new value
            parent (sdict): old&new_v's parent
            key: conflict happens when diff value with same key

        ## Send
            NEW_V: if you don't want to use new_v, you send your wanted value here
        """
        if isinstance(new, DeepDiff):
            new_data = getattr(new, "t2", None)
            if not isinstance(new_data, Mapping):
                raise TypeError(f"`New.t2` must be Mapping, got {type(new_data)!r}")
            diff = new
        elif isinstance(new, Mapping):
            new_data = self.__class__(new)
            diff = DeepDiff(
                self,
                new_data,
                # ignore_order only affect tuple/list, no orderedDict, so we need manually re-sort
                ignore_order=False,
                ignore_type_in_groups=[(Mapping, MutableMapping)],
            )
        else:
            raise TypeError(f"`New` must be Mapping or DeepDiff, got {type(new)!r}")
        if not diff and order != "new":
            if conflict is not None:
                return self

        # TODO: cleanup AI code
        def _reorder(parent_old: MutableMapping, parent_new: Mapping):
            if order != "new":
                return
            ordered_keys = []
            for k in parent_new.keys():
                if k in parent_old:
                    ordered_keys.append(k)
            for k in parent_old.keys():
                if k not in parent_new:
                    ordered_keys.append(k)
            ordered_items = [(k, parent_old[k]) for k in ordered_keys]
            parent_old.clear()
            parent_old.update(ordered_items)

        def _iter_path(change):
            if change is None:
                return ()
            if isinstance(change, Mapping):
                return change.keys()
            return change

        def _collapse_path(path: str) -> tuple[Any, ...]:
            steps = tuple(parse_path(path))
            merged: list[Any] = []
            for step in steps:
                merged.append(step)
                old_next = self.getitem(merged, default=UNSET)
                new_next = get_item(
                    new_data,
                    merged,
                    default=UNSET,
                    noRaise=(KeyError, IndexError, TypeError),
                )
                if not (
                    isinstance(old_next, MutableMapping)
                    and isinstance(new_next, Mapping)
                ):
                    break
            return tuple(merged)

        add_paths = {
            _collapse_path(path)
            for path in _iter_path(diff.get("dictionary_item_added"))
        }
        conflict_paths = {
            _collapse_path(path)
            for change_type in (
                "values_changed",
                "type_changes",
                "iterable_item_added",
                "iterable_item_removed",
                "set_item_added",
                "set_item_removed",
                "repetition_change",
            )
            for path in _iter_path(diff.get(change_type))
        }
        add_paths.discard(())
        conflict_paths.discard(())
        changed_prefixes = {
            path[:i]
            for path in (*add_paths, *conflict_paths)
            for i in range(1, len(path) + 1)
        }

        def _merge_gen(parent_old: MutableMapping, parent_new: Mapping, prefix=()):
            for key, new_v in parent_new.items():
                path = (*prefix, key)
                if (
                    order != "new"
                    and path not in changed_prefixes
                    and key in parent_old
                ):
                    continue
                if key not in parent_old:
                    parent_old[key] = new_v
                    continue

                old_v = parent_old[key]
                if isinstance(old_v, MutableMapping) and isinstance(new_v, Mapping):
                    if order == "new" or path in changed_prefixes:
                        yield from _merge_gen(old_v, new_v, path)
                    continue

                if path not in conflict_paths:
                    continue

                if conflict == "old":
                    continue
                if conflict == "new":
                    parent_old[key] = new_v
                    continue

                NEW_V = yield old_v, new_v, parent_old, key
                if NEW_V is not None:
                    if NEW_V is NONE:
                        NEW_V = None
                    parent_old[key] = NEW_V

            _reorder(parent_old, parent_new)

        gen = _merge_gen(self, new_data)
        if conflict is not None:
            for _ in gen:
                pass
            self.del_cache()
            return self

        def _runner():
            yield from gen
            self.del_cache()
            return self

        return _runner()

    def keys_flat(
        self,
        maxDepth=float("inf"),
        digList=True,
        slice: slice[int | None] = slice(None),
        getChild: GetChildFunc = get_children,
        **kwargs,
    ):
        """
        like benedict.keypaths()
        Args:
            digList: set False if you only want dict-dict-dict, instead of dict-list-dict...
            **kwargs: passed to `dfs()`
        """
        for K, _ in self.items_flat(
            maxDepth=maxDepth, digList=digList, slice=slice, getChild=getChild, **kwargs
        ):
            yield K

    def values_flat(
        self,
        maxDepth=float("inf"),
        digList=True,
        slice: slice[int | None] = slice(None),
        getChild: GetChildFunc = get_children,
        **kwargs,
    ):
        """
        Args:
            digList: set False if you only want dict-dict-dict, instead of dict-list-dict...
            **kwargs: passed to `dfs()`
        """
        for _, v in self.items_flat(
            maxDepth=maxDepth, digList=digList, slice=slice, getChild=getChild, **kwargs
        ):
            yield v

    def items_flat(
        self,
        maxDepth=float("inf"),
        digList=True,
        slice: slice[int | None] = slice(None),
        getChild: GetChildFunc = get_children,
        **kwargs,
    ):
        """
        Args:
            digList: set False if you only want dict-dict-dict, instead of dict-list-dict...
            **kwargs: passed to `dfs()`
        """
        if digList is False:
            getChild = get_children_noList
        for v in self.dfs(maxDepth=maxDepth, getChild=getChild, **kwargs):
            if isinstance(v, self.__class__) and in_range(v.depth, slice):
                for kp in itertools.product(*v.keypath):
                    yield kp, v  # TODO: need test

    def dfs(
        self,
        maxDepth=float("inf"),
        yieldIf: YieldIfFunc | None = None,
        getChild: GetChildFunc = get_children,
        readonly=False,
        **kwargs,
    ) -> Generator[Self, Any, Self | Any]:
        """
        see `dfs(**kwargs)`
        """
        return dfs(
            self.v,
            maxDepth=maxDepth,
            yieldIf=yieldIf,
            getChild=getChild,
            readonly=readonly,
            **kwargs,
        )

    def insert(
        self,
        update: Mapping[K, V],
        key: K | UNSET = UNSET,
        index: int | None = None,
        after=False,
    ):
        """insert the `update` dict before `key` or `index`"""
        if key is UNSET and index is None:
            raise ValueError("key or index must be set")
        if not update:
            return

        keys_before_update = list(self.keys())

        target_index = -1
        if index is not None:
            target_index = index if index >= 0 else len(keys_before_update) + index
            target_index = max(0, min(target_index, len(keys_before_update)))
        elif key is not UNSET:
            try:
                target_index = self.index(key)
                if after:
                    target_index += 1
            except (ValueError, TypeError):
                raise KeyError(key, "not found")

        for k, v in update.items():
            self[k] = v
            self.move_to_end(k)

        for k in keys_before_update[target_index:]:
            if k not in update:
                self.move_to_end(k)
        self.del_cache()

    def index(self, key: K | UNSET = UNSET, value: V | UNSET = UNSET) -> int:
        if key is UNSET and value is UNSET:
            raise ValueError("key or value must be set")
        if key is not UNSET:
            try:
                return list(self.keys()).index(key)
            except ValueError:
                raise ValueError(f"Key {key!r} not found")
        else:
            try:
                return list(self.values()).index(value)
            except ValueError:
                raise ValueError(f"Value {value!r} not found")

    # TODO cache?
    def i_to_k(self, index: int) -> K:
        """index to key"""
        return tuple(self.keys())[index]

    def v_to_k(self, value: V):
        """value to keys"""
        for k, v in self.items():
            if v == value:
                yield k

    def sort(
        self,
        key: Callable[[K], Any] | None = None,
        reverse: bool = False,
    ):
        items = list(self.items())
        if key is None:
            items.sort(key=lambda item: item[0], reverse=reverse)
        else:
            items.sort(key=lambda item: key(item[0]), reverse=reverse)
        self.clear()
        self.update(items)

    def count(self, value: V) -> int:
        return list(self.values()).count(value)

    @property
    def depth(self):
        """from root"""
        return len(self.keypath)  # len(self.pathCount)

    @cached_property
    def height(self):
        """
        from leaves
        currently not implement signal dict like angular, so you need manually del cache
        """
        return max(k for k in self.keys_flat())

    @cached_property
    def childkeys(self):
        """
        `del sdict.childkeys` to refresh cache
        currently not implement signal dict like angular, so you need manually del cache
        """
        return tuple(dfs(self.v, maxDepth=1))
