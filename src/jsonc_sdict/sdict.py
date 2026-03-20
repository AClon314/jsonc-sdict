"""
super dict, signal dict...
"""

from dataclasses import dataclass

import re
import itertools
from weakref import ref
from collections import OrderedDict
from functools import cached_property, partial
from types import MappingProxyType
from typing import (
    cast,
    get_args,
    overload,
    Any,
    Self,
    Unpack,
    Literal,
    TypedDict,
    TypeIs,
)
from collections.abc import (
    Callable,
    Hashable,
    Iterable,
    Generator,
    Mapping,
    MutableMapping,
    Sequence,
)


from jsonc_sdict.share import (
    UNSET,
    RAISE,
    NONE,
    copy_args,
    iterable,
    in_range,
    getLogger,
)
from jsonc_sdict.weakList import WeakList

type Key[K = Any, V = sdict] = K | int
"""sdict[ dict:Key | list:int-index ]"""
type KeyPaths[K = Any, V = Any] = tuple[list[Key[K, V]], ...]
"""[[parent1, parent2(depth==0)], [me,(depth==1)], [child1, child2, (depth==3) ...]]"""
type PathCount = tuple[int, ...]
type Node[K = int, V = Any] = Mapping[K, V] | Iterable[V]


type NestDict[K = str, Leaf = Any] = "dict[K, NestDict[K, Leaf] | Leaf]"
type NestSDict[K = str, Leaf = Any] = "sdict[K, NestSDict[K, Leaf] | Leaf]"
type NestMap[K = str, Leaf = Any] = "Mapping[K, NestMap[K, Leaf] | Leaf]"
type NestMutMap[K = str, Leaf = Any] = "MutableMapping[K, NestMutMap[K, Leaf] | Leaf]"
type NestDictList[K = str, Leaf = Any] = (
    "dict[K, list[NestDictList[K, Leaf]] | list[Leaf]]"
)
type NestMapIter[K = str, Leaf = Any] = (
    "Mapping[K, Iterable[NestMapIter[K, Leaf]] | Iterable[Leaf]]"
)

Log = getLogger(__name__)

# ------------------------------------------------------------
# recursive get
# ------------------------------------------------------------


def get_item[K, D](
    obj: NestMutMap[K],
    keys: Iterable[K],
    default: D = RAISE,
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
    if default is RAISE:
        noRaise = ()
    if not iterable(keys):
        return obj[keys]  # type: ignore
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
    default: D = RAISE,
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
    if default is RAISE:
        noRaise = ()
    if not iterable(keys):
        return getattr(obj, keys)  # type: ignore
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
    default: D = RAISE,
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
    if default is RAISE:
        noRaise = ()
    if not iterable(keys):
        if hasattr(obj, "__getitem__"):
            return obj[keys]
        else:
            return getattr(obj, keys)  # type: ignore
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
    parent = get_item_attr(obj, keys[:-1])
    k = keys[-1]
    if hasattr(obj, "__setitem__"):
        parent[k] = value  # type: ignore
    else:
        setattr(parent, k, value)


def set_item(obj, keys: Sequence, value) -> None:
    """see `get_item()` & `get_item_attr()`"""
    parent = get_item(obj, keys[:-1])
    parent[keys[-1]] = value  # type: ignore


def del_item_attr(obj, keys: Sequence) -> None:
    """see `set_item_attr()`"""
    if not iterable(keys):
        if hasattr(obj, "__delitem__"):
            del obj[keys]
        else:
            delattr(obj, keys)
        return
    parent = get_item_attr(obj, keys[:-1])
    k = keys[-1]
    if hasattr(obj, "__delitem__"):
        del parent[k]  # type: ignore
    else:
        delattr(parent, k)


def del_item(obj, keys: Sequence) -> None:
    """see `set_item_attr()`"""
    parent = get_item(obj, keys[:-1])
    del parent[keys[-1]]  # type: ignore


# ------------------------------------------------------------
# dfs
# ------------------------------------------------------------


def get_children[K, V](
    self: "sdict[K, V] | Any", raw: Node[K, V] | Any, digList=True
):  # -> Generator[Iterable[K,V], None, None] | Generator[Iterable[tuple[int, V]], None, None]:
    """
    default getChild func
    Args:
        self: maybe sdict that holding raw in `dfs()`, or Any
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
    [sdict[K, V] | Any, Node[K, V]], Generator[Iterable[V], None, None] | Iterable[V]
]

type SetValueFunc = Callable[[Any, Sequence, Any], Any]


class _KwargsDfs3(TypedDict, total=False):
    parents: WeakList[Self]
    keypaths: KeyPaths
    pathCount: PathCount


class KwargsDfs(_KwargsDfs3, total=False):
    # obj: Node
    maxDepth: int | float
    cls: type[Self] | None
    yieldIf: YieldIfFunc | None
    getChild: GetChildFunc
    readonly: bool
    setValue: SetValueFunc


def dfs[K = int, V = Any, CLS = "sdict"](
    obj: Node[K, V],
    maxDepth=float("inf"),
    cls: type[CLS] | None = None,
    yieldIf: YieldIfFunc | None = None,
    getChild: GetChildFunc = get_children,
    readonly=False,
    setValue: SetValueFunc = set_item_attr,
    *,
    parent: WeakList = WeakList(),
    keypaths: KeyPaths = (),
    pathCount: PathCount = (0,),
) -> Generator[CLS]:
    """
    do NOT update scaned/yielded data while iterating.
    Args:
        maxDepth: stop digging if deeper
        yieldIf: yield only if yield_if(self, node) is True
        getChild: see `get_children()`
        readonly: if True, will
            - not update sdict's `parent`, `keypath`, `pathCount` if already dfs(sdict)
            - yield in `sdict.ref`, not `sdict`, keep original Map instance if you want to invoke its method
            - not substitute {"children": container[...]} to {"children": list[sdict]}
    Usage:
    ```python
    for node in dfs(myDict):
        ...

    # if you offen dfs the same dict-object twice or even more, use cache:
    from jsonc_sdict import dfs, copy_args
    dfs_cache = lru_cache(maxsize=4096)(dfs)
    # if you like some type hint:
    # dfs_cache = copy_args(dfs)(lru_cache(maxsize=4096)(dfs))
    for node in dfs_cache(myDict):
        ...
    ```
    """
    # print(f"{type(obj)=}")
    if not iterable(obj) or len(keypaths) > maxDepth:
        return obj
    if cls is None:
        cls = sdict  # type: ignore

    pathCount = (*pathCount[:-1], pathCount[-1] + 1)
    if isinstance(obj, sdict) and not readonly:
        # update
        obj.parents = parent
        obj.keypaths = keypaths
        obj.pathCount = pathCount
        self = obj
    else:
        data = None
        ref = None
        if isinstance(obj, Mapping) and not readonly:
            data = obj
        else:
            # list / pydantic
            ref = obj
        # cls = cast(type[sdict], cls)
        self = cls(  # type: ignore
            data=data,
            ref=ref,
            # deep==True等价于执行dfs()，所以False即可
            deep=False,
            parent=parent,
            keypaths=keypaths,
            pathCount=pathCount,
        )
    self = cast(sdict, self)
    newSelf = None
    if yieldIf is None or yieldIf(self, obj):
        newSelf = yield self
    if newSelf is not None:
        self = None if newSelf is NONE else newSelf
    children = getChild(self, obj)
    for i, (k, v) in enumerate(children):
        if not iterable(v):
            continue
        _parent = WeakList((self,))
        _keypaths = (*keypaths, [k])
        _pathCount = (*pathCount, i)
        ret = yield from dfs(
            v,
            maxDepth=maxDepth,
            cls=cls,
            yieldIf=yieldIf,
            getChild=getChild,
            readonly=readonly,
            setValue=setValue,
            parent=_parent,
            keypaths=_keypaths,
            pathCount=_pathCount,
        )
        if not readonly:
            # substitute python dict to sdict
            setValue(self, k, ret)  # self[k] = ret
    return self


@dataclass
class ddYield:
    """yield of dictDict()"""

    v: Any
    self: "sdict"
    """you should use `if newKey in self` to prevent duplicate key, otherwise `update()` would **overwrite** old value"""


class KwargsDictDict(TypedDict, total=False):
    idKey: Any
    """idKey: the keyname of unique value in dict. If not found, will raise"""
    getValue: Callable[[Any, Any], Any]
    """getValue(current_dict, idKey): get idKey of dict"""


def dictDict(
    gen: Generator,
    idKey: Any = UNSET,
    getValue: Callable[[Any, Any], Any] = get_item_attr,
) -> Generator[ddYield, Hashable, tuple[NestSDict, list[tuple]]]:
    """
    list[dict[list...]] or dict[list[dict...]] to pure nest dict like dict[dict[dict...]].
    use before `merge()`, because list[dict] is hard to merge correctly(while list[Scalar] or dict[...] is easy)

    ```python
    for sdic in (idKey := dictDict(dfs(obj), idKey="id")):
        # will auto update {..., children: [{"id":123},...]} to {..., children: {123:{...}, ...}}
        # but if not found the idKey, will raise KeyError

    for sdic in (idKey := dictDict(dfs(obj)):
        if isinstance(sdic.v, MyType):
            idKey.send("another-IdKey")
        else:
            pass # idKey.send(None)
            # we use `id()` for fallback idKey, or `(id(), counter)` when id() is not unique
    ```

    Args:
        obj: dict or list, Map or Iterable
        idKey: the keyname of unique value in dict. If not found, will raise
        getValue(current_dict, idKey): get idKey of dict

    Raises:
        KeyError: when all idKey is not found
    """
    # TODO: record in undoKeys to restore to original data structure for `merge()`
    undoKeys = []

    def _yield(self: sdict, v):
        key = yield ddYield(v=v, self=self)
        if key is NONE:
            key = None
        elif key is None:
            if idKey is UNSET:
                key = id(v)
                if key in self:
                    raise NotImplementedError(
                        "rare edge case, click https://github.com/AClon314/jsonc-sdict/issues to report"
                    )
            else:
                key = getValue(v, idKey)
        self.update({key: v})
        # gen.send(self) # TODO: 似乎执不执行，结果都一样？

    while self := next(gen):
        if not isinstance(self, sdict):
            raise TypeError("only support dictDict(gen= dfs(cls=sdict) )")
        if self.use_ref:
            if iterable(self.ref):
                for v in self.ref:
                    yield from _yield(self, v)
            else:
                yield from _yield(self, self.ref)
            undoKeys.append(self.keypath)  # TODO
            # undoKeys.append(list(itertools.product(*self.keypaths))[-1])  # TODO
            self.use_ref = False
            self.ref = None
    return self, undoKeys


# ------------------------------------------------------------
# unref
# ------------------------------------------------------------


def unref(obj, const=False, memo: dict[int, Any] | None = None):
    """
    Args:
        const: return tuple/MappingProxyType if const else list/dict,
        memo: just leave default, internal {id(): value}
    """
    if memo is None:
        memo = {}
    value = obj.v if isinstance(obj, sdict) else obj
    if not (isinstance(value, Mapping) or iterable(value)):
        return value

    obj_id = id(value)
    if obj_id in memo:
        return memo[obj_id]

    if isinstance(value, Mapping):
        out = {}
        memo[obj_id] = out
        for k, v in value.items():
            out[k] = unref(v, const=const, memo=memo)
        if const:
            frozen = MappingProxyType(out)
            memo[obj_id] = frozen
            return frozen
        return out

    out_list = []
    memo[obj_id] = out_list
    out_list.extend(unref(v, const=const, memo=memo) for v in value)
    if const:
        frozen = tuple(out_list)
        memo[obj_id] = frozen
        return frozen
    return out_list


class sdict[K = str, V = Any, R = Any](OrderedDict[K, V]):
    """
    search-friendly dict, or "dict design for json in actual business", like benedict, but less limitation, more useful context, more strict type hint.

    Generic 泛型:
        K,V: the current depth that Key,Value's type \n
            当前层级的 Key, Value 键值类型
        R: type of self.ref
    """

    type IterAsMap = Iterable[tuple[K, V]]

    class _KwargsInit(TypedDict, total=False):
        # data: Mapping[K, V] | None
        ref: R | None
        deep: bool
        parent: WeakList[Self]
        keypaths: KeyPaths[Any, Self]
        pathCount: PathCount
        getChild: GetChildFunc

    def __init__(
        self,
        data: Mapping[K, V] | IterAsMap | Any | None = None,
        ref: R | None = None,
        *,
        deep=True,
        parents: WeakList[Self] = WeakList(),
        keypaths: KeyPaths[Any, Self] = (),
        pathCount: PathCount = (0,),
        getChild: GetChildFunc = get_children,
    ):
        """
        Args:
            data: init dictionary, which unpack and create **shallow** copy (👍recommended, full-feature)
                if is `sdict`, use `deepcopy(mySdict)` or `copy(mySdict)` to keep internal states
            ref: +1 reference\n
                `sdict(ref=myPydanticModel)` # keep `myPydanticModel` instance's orginal methods\n
                `s=sdict(ref=ref(hashableObj)); s.ref()` # return **None** after `del hashableObj`\n
                `s=sdict(ref=proxy(hashableObj)); s.ref` # raise **ReferenceError** after `del hashableObj`
            deep: exec `dfs()`/`sdict.rebuild()`, create **deep** copy, slower when init
            parent: weakref of parent
            getChild: used for __getitem__
        """
        if isinstance(data, sdict):
            Log.warning(
                "{} is sdict, use deepcopy(mySdict) or copy(mySdict) to keep internal states",
                type(data),
            )

        self.repr = False
        """if you want `{}`, set to False; if you want `sdict({})` truly raw data, set to True"""
        self.use_ref = data is None
        """affect the return of self.v"""
        super().__init__(data or ())
        self.ref = ref
        """can storage pydantic_model_data, list_data..."""
        self.parents = parents
        self.keypaths = keypaths
        """from root"""
        self.pathCount = pathCount
        if deep:
            self.rebuild()

    def rebuild(self):
        """build index/cache entirely.\n
        currently I recommand re-init a sdict instance if you want to **treat a child as new root node**, by `sdict(myChild_as_NewRoot_oldSdict)`
        """
        for _ in dfs(
            self,
            parent=self.parents,
            keypaths=self.keypaths,
            pathCount=self.pathCount,
        ):
            pass
        self.del_cache()

    type _Cached = Literal["height", "childkeys", "unref"]

    def del_cache(self, without: Iterable[_Cached] = ()):
        todo = self._cached - set(without)
        for attr in todo:
            try:
                delattr(self, attr)
            except AttributeError:
                pass

    def __init_subclass__(cls) -> None:
        cls._cached = set(get_args(cls._Cached))

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

    @cached_property
    def unref(self):
        """deep unref all `sdict.v`, used for `json.dumps(sd.unref)`"""
        return unref(self.v)

    @staticmethod
    def is_nestKeys(key: Any) -> TypeIs[Sequence]:
        return isinstance(key, Sequence) and not isinstance(
            key, (str, bytes, bytearray)
        )

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

    @overload
    def __getitem__(self, key: slice) -> list[Any]: ...

    @overload
    def __getitem__(self, key: Any) -> Any: ...

    def __getitem__(self, key: K | Iterable[K] | slice | Any):
        """
        - before rebuild(), return actual value
        - after rebuild(), return `sdict` that wraps actual value
        """
        if isinstance(key, slice):
            v = [x for x in self.values_flat(slice=key)]
        elif self.use_ref or self.is_nestKeys(key):
            # key is list / tuple
            v = self.getitem(key)
        else:
            # key = cast(K, key)
            v = super().__getitem__(key)
        return v

    def setitem(self, key: Sequence[K], value, at=UNSET):
        """see `set_item_attr()`"""
        return set_item_attr(self.v if at is UNSET else at, key, value)

    def __setitem__(self, key: K | Sequence[K] | slice | Any, value):
        if isinstance(key, slice):
            raise NotImplementedError("TODO")  # TODO: batch
            for i in self.keys_flat(slice=key):
                self[i] = value
        elif self.use_ref or self.is_nestKeys(key):
            self.setitem(key, value)
        else:
            super().__setitem__(key, value)
        self.del_cache()

    def delitem(self, key: Sequence[K], at=UNSET):
        """see `del_item_attr()`"""
        return del_item_attr(self.v if at is UNSET else at, key)

    def __delitem__(self, key: K | Sequence[K] | slice | Any):
        if isinstance(key, slice):
            raise NotImplementedError("TODO")  # TODO: batch
            for i in self.keys_flat(slice=key):
                del self[i]
        elif self.use_ref or self.is_nestKeys(key):
            self.delitem(key)
        else:
            super().__delitem__(key)
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
            if not self.parents or not self.keypaths:
                raise KeyError(new, "not found")
            parent = self.parents[-1]
            old = self.keypaths[-1][-1]
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

        def _rename_parent(parent: Self) -> bool:
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

    # TODO: merge

    def keys_flat(
        self,
        maxDepth=float("inf"),
        digList=True,
        slice: slice = slice(None),
        getChild: GetChildFunc = get_children,
        **kwargs: Unpack[_KwargsDfs3],
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
        slice: slice = slice(None),
        getChild: GetChildFunc = get_children,
        **kwargs: Unpack[_KwargsDfs3],
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
        slice: slice = slice(None),
        getChild: GetChildFunc = get_children,
        **kwargs: Unpack[_KwargsDfs3],
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
                for kp in itertools.product(*v.keypaths):
                    yield kp, v  # TODO: need test

    def dfs(
        self,
        maxDepth=float("inf"),
        yieldIf: YieldIfFunc | None = None,
        getChild: GetChildFunc = get_children,
        readonly=False,
        setValue=set_item,
        **kwargs: Unpack[_KwargsDfs3],
    ) -> Generator[Self, Any, Self | Any]:
        """
        see `dfs(**kwargs)`
        """
        return dfs(  # type: ignore
            self.v,
            cls=self.__class__,  # type: ignore
            maxDepth=maxDepth,
            yieldIf=yieldIf,
            getChild=getChild,
            readonly=readonly,
            setValue=setValue,
            **kwargs,
        )

    def insert(
        self,
        update: Mapping[K, V],
        key: K | UNSET = UNSET,
        index: int | None = None,
        after=False,
    ) -> None:
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
            except (ValueError, TypeError) as e:
                raise KeyError(key, "not found") from e

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
            except ValueError as e:
                raise ValueError(f"Key {key!r} not found") from e
        else:
            try:
                return list(self.values()).index(value)
            except ValueError as e:
                raise ValueError(f"Value {value!r} not found") from e

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
    def keypath(self) -> tuple:  # TODO list or tuple?
        return list(itertools.product(*self.keypaths))[-1]

    @property
    def parent(self):
        return self.parents[-1] if self.parents else None

    @property
    def depth(self):
        """from root"""
        return len(self.keypaths)  # len(self.pathCount)

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
