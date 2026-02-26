"""
because list is not hashable, so list is designed for:
- don't treat like key name: see `type Key`
"""

from weakref import ref
from collections import UserDict
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Generator
from functools import cached_property, partial
from typing import Any, TypeGuard, cast

from jsonc_sdict.share import in_range
from jsonc_sdict.weakList import WeakList

type Key[K = Any, V = sdict] = K | int | list[Callable[[V], bool]]
"""jdict[ dict:Key | list:int-index | dict:[mySelectFunc(value)->bool] ]"""
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


def get_item[D](
    obj,
    keys: Iterable,
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


def iterable[V](obj: Iterable[V] | Any) -> TypeGuard[Iterable[V]]:
    """Iterable but NOT str, bytes"""
    return isinstance(obj, Iterable) and not isinstance(obj, (str, bytes))


def get_children[K, V](
    self: "sdict[K, V]", raw: Node[K, V], digList=True
) -> Generator[Iterable[V], None, None]:
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
        children = raw.__dict__
    elif digList:
        # list
        children = enumerate(raw)
    return (v for v in children if iterable(v))


get_children_noList = partial(get_children, digList=False)
"""get_children(..., digList=False)"""

type GetChildFunc[K, V] = Callable[
    [sdict[K, V], Node[K, V]], Generator[Iterable[V], None, None] | Iterable[V]
]


def dfs[K = int, V = Any, KP = str](
    obj: Node[K, V],
    maxDepth=float("inf"),
    getChild: GetChildFunc = get_children,
    *,
    parent: WeakList["sdict"] = WeakList(),
    keypath: KeyPaths = (),
    pathCount: PathCount = (0,),
):
    """
    do NOT update scaned/yielded data while iterating.
    Args:
        maxDepth: stop digging if deeper
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
    print(f"{type(obj)=}")
    if not iterable(obj) or len(keypath) > maxDepth:
        return obj

    self = None
    pathCount = (*pathCount[:-1], pathCount[-1] + 1)
    if isinstance(obj, sdict):
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
    yield self
    children = getChild(self, obj)
    for i, (k, v) in enumerate(children):
        _parent = WeakList((self,))
        _keypath = (*keypath, [k])
        _pathCount = (*pathCount, i)
        ret = yield from dfs(
            v,
            maxDepth=maxDepth,
            getChild=getChild,
            parent=_parent,
            keypath=_keypath,
            pathCount=_pathCount,
        )
        # substitute python dict to sdict
        self[k] = ret
    return self


class sdict[K = str, V = Any, R = Any, KP = Any](UserDict[K, V]):
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
        return self.ref if self.data is None else self.data\n
        will unpack weakref.ref
        """
        if self.data is not None:
            return self.data
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
    ):
        """
        Args:
            data: `self.data = {**data}`, which unpack and create **shallow** copy (👍recommended, full-feature)
            ref: +1 reference\n
                `sdict(ref=myPydanticModel)` # keep `myPydanticModel` instance's orginal methods\n
                `s=sdict(ref=ref(hashableObj)); s.ref()` # return **None** after `del hashableObj`\n
                `s=sdict(ref=proxy(hashableObj)); s.ref` # raise **ReferenceError** after `del hashableObj`
            deep: exec `dfs()`/`sdict.rebuild()`, create **deep** copy, slower when init
            parent: weakref of parent
        """
        super().__init__(data)
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
        # rebuild cache
        try:
            del self.height
        except AttributeError:
            pass
        try:
            del self.childkeys
        except AttributeError:
            pass

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
        if iterable(key) and not isinstance(key, Mapping):
            v = self.getitem(key, noRaise=())
        elif isinstance(key, slice):
            v = list(self.values_flat(key))
        else:
            key = cast(K, key)
            v = super().__getitem__(key)
        return (
            self.__class__(v, deep=False)
            if not isinstance(v, sdict) and isinstance(v, Mapping)
            else v
        )

    def __hash__(self):
        return id(self)

    # def __eq__(self, value: object) -> bool:
    #     if isinstance(value, sdict):
    #         return self.v == value.v
    #     return self.v == value

    # def __repr__(self) -> str:
    #     return f"{self.__class__.__name__}({self.v!r})"

    def keys_flat(self, slice: slice[int | None] = slice(None), digList=True, **kwargs):
        """
        like benedict.keypaths()
        Args:
            digList: set False if you only want dict-dict-dict, instead of dict-list-dict...
            **kwargs: passed to `dfs()`
        """
        for K, _ in self.items_flat(slice=slice, digList=digList, **kwargs):
            yield K

    def values_flat(
        self, slice: slice[int | None] = slice(None), digList=True, **kwargs
    ):
        """
        Args:
            digList: set False if you only want dict-dict-dict, instead of dict-list-dict...
            **kwargs: passed to `dfs()`
        """
        for _, v in self.items_flat(slice=slice, digList=digList, **kwargs):
            yield v

    def items_flat(
        self,
        slice: slice[int | None] = slice(None),
        digList=True,
        getChild=get_children,
        **kwargs,
    ) -> Generator[tuple[KeyPaths[KP, "sdict"], "sdict"]]:
        """
        Args:
            digList: set False if you only want dict-dict-dict, instead of dict-list-dict...
            **kwargs: passed to `dfs()`
        """
        if not digList:
            getChild = get_children_noList
        for v in dfs(self.v, getChild=getChild, **kwargs):
            if isinstance(v, sdict) and in_range(v.depth, slice):
                yield v.keypath, v

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

    def dfs(self, childKeys: tuple[str, ...] = (), maxDepth=float("inf"), List=True):
        """
        Args:
            childKeys: ('children','catalogs',), which will only dig into these key, use this to speed up if you already known your data format
            maxDepth: stop digging if deeper
            List: whether to dig into list-like object. like `bdict.keypaths(indexes=<bool>)` in benedict
        """
        return dfs(self.v)
