"""super dict, signal dict."""

import re
from weakref import ref, WeakKeyDictionary, WeakValueDictionary
from dataclasses import dataclass
from collections import OrderedDict
from functools import cached_property, partial
from types import MappingProxyType
from typing import (
    Never,
    cast,
    overload,
    Any,
    Self,
    Unpack,
    TypeIs,
    Literal,
    TypedDict,
    TYPE_CHECKING,
)
from collections.abc import (
    Callable,
    Hashable,
    Iterable,
    Generator,
    Mapping,
    Sequence,
    MutableMapping,
    MutableSequence,
    MutableSet,
    Iterator,
)


from jsonc_sdict.share import (
    UNSET,
    RAISE,
    NONE,
    copy_args,
    args_of_type,
    isFlatIterable,
    iterable,
    iSlice,
    in_range,
    are_equal,
    getLogger,
    _TODO,
)
from jsonc_sdict.weakList import WeakList

if TYPE_CHECKING:
    from jsonc_sdict.Merge import merge as _merge

type Key[K = Any] = K | int
"""dict:Key | list:int-index"""
type ForkGraph[K = Any, V = "sdict"] = WeakKeyDictionary[
    V, WeakValueDictionary[Key[K], V]
]
"""{parent_1: {parentKeys_2: self_3}}, eg: {root1: {key2: son3, key22: son3}, son3: {key4: grandson5}}}, strictly require root -> parent -> children order."""
type PathCount = tuple[int, ...]
type Node[K = int, V = Any] = Mapping[K, V] | Iterable[V]


type NestDict[K = Any, Leaf = Any] = "dict[K, NestDict[K, Leaf] | Leaf]"
type NestSDict[K = Any, Leaf = Any] = "sdict[K, NestSDict[K, Leaf] | Leaf]"
type NestMap[K = Any, Leaf = Any] = "Mapping[K, NestMap[K, Leaf] | Leaf]"
type NestMutMap[K = Any, Leaf = Any] = "MutableMapping[K, NestMutMap[K, Leaf] | Leaf]"
type NestDictList[K = Any, Leaf = Any] = (
    "dict[K, list[NestDictList[K, Leaf]] | list[Leaf]]"
)
type NestMapIter[K = Any, Leaf = Any] = (
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
    if not keys:
        return obj
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
    if not keys:
        return obj
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
        # if not container, just directly return (如果不是容器，直接返回)
        if hasattr(obj, "__getitem__"):
            return obj[keys]
        else:
            return getattr(obj, keys)  # type: ignore
    if not keys:
        # if at root, just return itself (如果是根容器，直接返回自自身)
        return obj
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
    if not keys:
        # if at root, try to update itself (如果是根容器，尝试更新自己)
        if hasattr(obj, "__setitem__"):
            obj.clear()
            if isinstance(obj, (MutableMapping, MutableSet)):  # need ordered_set
                obj.update(value)
            elif isinstance(obj, MutableSequence):
                obj.extend(value)
            else:
                raise TypeError(
                    f"Failed to update {type(obj)=} at root level ({keys=})"
                )
        else:
            # TODO: need test
            obj.__dict__.clear()
            obj.__dict__.update(value.__dict__)
        return

    parent = get_item_attr(obj, iSlice(keys))
    k = keys[-1]
    if hasattr(obj, "__setitem__"):
        parent[k] = value  # type: ignore
    else:
        setattr(parent, k, value)


def set_item(obj, keys: Sequence, value) -> None:
    """see `get_item()` & `get_item_attr()`"""
    parent = get_item(obj, iSlice(keys))
    parent[keys[-1]] = value  # type: ignore


def del_item_attr(obj, keys: Sequence) -> None:
    """see `set_item_attr()`"""
    if not iterable(keys):
        if hasattr(obj, "__delitem__"):
            del obj[keys]
        else:
            delattr(obj, keys)
        return
    parent = get_item_attr(obj, iSlice(keys))
    k = keys[-1]
    if hasattr(obj, "__delitem__"):
        del parent[k]  # type: ignore
    else:
        delattr(parent, k)


def del_item(obj, keys: Sequence) -> None:
    """see `set_item_attr()`"""
    parent = get_item(obj, iSlice(keys))
    del parent[keys[-1]]  # type: ignore


# ------------------------------------------------------------
# pathGraph
# ------------------------------------------------------------


class NodeKeyDict[K, N = "sdict"](WeakKeyDictionary[N, K]):
    """
    - `.keys()`/`.nodePath` will get node-path
    - `.values()[:-1]`/`.keypath` will get keypath, without the last empty key.
    """

    cycleStartNode: ref[N]

    @property
    def cycleStartKey(self) -> None | K:
        node = self.cycleStartNode()
        return None if node is None else self[node]

    @property
    def nodePath(self) -> Iterator[N]:
        return self.keys()

    @property
    def keypath(self) -> tuple[K, ...]:
        return tuple(self.values())[:-1]


def all_path[K, V = "sdict"](
    forkGraph: ForkGraph[K, V],
    target: V | None = None,
) -> Generator[NodeKeyDict[K, V], Never, None]:
    """
    Enumerate all root-to-leaf paths in `graph`. Similar to `networkx.DiGraph.all_simple_path()`.

    When `target` is provided, stop traversal once a path reaches that node and yield
    root-to-target prefixes instead. If `target` is not found in `forkGraph`, yield the
    isolated `{target: NONE}` path.

    Each yielded path is an ordered weak mapping of `{node: key_in_node}`:
    - `{leaf_node: NONE}` for a normal leaf
    - `cycleStartNode = ref(node)` when the path ends by closing a cycle

    The persistent forkGraph cache stays weakly referenced in `graph`, while DFS state
    here uses a plain stack and an active-node index so push/pop order and cycle
    detection remain explicit.
    """
    if not forkGraph:
        if target is not None:
            result = NodeKeyDict()
            result[target] = NONE
            yield result
        return
    graph_node_ids = {id(node) for node in forkGraph.keys()}
    child_node_ids = {
        id(child) for children in forkGraph.values() for child in children.values()
    }
    start_nodes = [node for node in forkGraph.keys() if id(node) not in child_node_ids]
    if not start_nodes:
        start_nodes = list(forkGraph.keys())

    path: list[tuple[V, K | int | NONE]] = []
    active_index: dict[int, int] = {}
    seen_target_paths: set[tuple[int, ...]] = set()
    yielded_target = False

    def _emit(end: V | None = None, cycle_start: V | None = None):
        result = NodeKeyDict(path)
        if end is not None:
            result[end] = NONE
        if cycle_start is not None:
            result.cycleStartNode = ref(cycle_start)
        # roots.append(result)
        return result

    def _walk(node: V):
        nonlocal yielded_target
        if node is target:
            result = _emit(end=node)
            signature = tuple(id(n) for n in result.nodePath)
            if signature not in seen_target_paths:
                seen_target_paths.add(signature)
                yielded_target = True
                yield result
            return

        node_id = id(node)
        active_index[node_id] = len(path)
        children = forkGraph.get(node)
        if not children:
            if target is None:
                yield _emit(end=node)
        else:
            for edge_key, child in children.items():
                path.append((node, edge_key))
                child_id = id(child)
                if child is target:
                    result = _emit(end=child)
                    signature = tuple(id(n) for n in result.nodePath)
                    if signature not in seen_target_paths:
                        seen_target_paths.add(signature)
                        yielded_target = True
                        yield result
                elif child_id in active_index:
                    yield _emit(cycle_start=child)
                elif child_id in graph_node_ids:
                    yield from _walk(child)
                elif target is None:
                    yield _emit(end=child)
                path.pop()
        del active_index[node_id]

    for root in start_nodes:
        yield from _walk(root)
    if target is not None and not yielded_target:
        result = NodeKeyDict()
        result[target] = NONE
        yield result


# def traceGraph[K, V = "sdict"](
#     forkGraph: ForkGraph[K, V],
# ):
#     # TODO: 将forkGraph的 {parent: {keyInParent: child1, keyInParent2: child2}} 倒置为 {child1: {keyInParent: parent}, child2: {keyInParnet: parent}}
#     pass


# ------------------------------------------------------------
# dfs
# ------------------------------------------------------------


def get_children[K, V](
    self: Node[K, V], raw: Node[K, V] | Any, digList=True
) -> Iterable[tuple[K | int, V]]:
    """
    default getChild func
    Args:
        self (sdict|Any): sdict(raw) by `dfs()`
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


class dfs[K = int | Any, V = Any, CLS = "sdict"](Generator[CLS, CLS, CLS]):
    """
    do NOT update scaned/yielded data while iterating.
    Args:
        maxDepth: stop digging if deeper
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

    type GetChildFunc = Callable[
        ["sdict[K, V] | Any", Node[K, V]], Iterable[tuple[K, V]]
    ]

    type SetValueFunc = Callable[[Any, Sequence, Any], Any]

    def __init__(
        self,
        obj: Node[K, V],
        maxDepth=float("inf"),
        cls: type[CLS] | None = None,
        getChild: GetChildFunc = get_children,
        readonly=False,
        setValue: SetValueFunc = set_item_attr,
        *,
        pathSeenIds: set[int] | None = None,
        forkGraph: ForkGraph | None = None,
        keypath: tuple = (),
        pathCount: PathCount = (0,),
    ):
        self.obj = obj
        self.maxDepth = maxDepth
        self.cls = cls
        self.getChild = getChild
        self.readonly = readonly
        self.setValue = setValue
        self.pathSeenIds = pathSeenIds
        self.forkGraph = forkGraph
        self.keypath = keypath
        self.pathCount = pathCount
        self._iter = self._new_iter()
        self._iter_started = False

    def _new_iter(self) -> Generator[CLS, Any, CLS | Any | None]:
        # print(f"{type(obj)=}")
        obj = self.obj
        maxDepth = self.maxDepth
        cls = self.cls
        getChild = self.getChild
        readonly = self.readonly
        setValue = self.setValue
        pathSeenIds = self.pathSeenIds
        forkGraph = self.forkGraph
        keypath = self.keypath
        pathCount = self.pathCount
        if pathSeenIds is None:
            pathSeenIds = set()
        if forkGraph is None:
            forkGraph = WeakKeyDictionary()
        depth = len(pathCount) - 1
        if not iterable(obj) or depth > maxDepth:
            return obj
        if cls is None:
            cls = sdict  # type: ignore

        pathCount = (*pathCount[:-1], pathCount[-1] + 1)
        if isinstance(obj, cls) and not readonly:
            # update
            SELF = obj
        else:
            data = None
            ref = None
            if isinstance(obj, Mapping) and not readonly:
                data = obj
            else:
                # list / pydantic
                ref = obj
            cls = cast(type[sdict], cls)
            try:
                SELF = cls(  # type: ignore
                    data=data,
                    ref=ref,
                    # deep==True等价于执行dfs()，所以False即可
                    deep=False,
                    forkGraph=forkGraph,
                    pathCount=pathCount,
                )
            except Exception as e:
                Log.error(
                    f"{cls=} is not sdict, fallback to positional init", exc_info=e
                )
                SELF = cls(data if data else ref)
        SELF = cast(sdict, SELF)
        SELF.forkGraph = forkGraph
        SELF.keypath = keypath  # NOTE: overwrite cache
        SELF.pathCount = pathCount

        newSelf = yield SELF
        if newSelf is not None:
            SELF = None if newSelf is NONE else newSelf
        if depth >= maxDepth:
            return SELF

        children = getChild(SELF, obj)
        pathSeenIds = pathSeenIds | {id(obj)}
        for i, (k, v) in enumerate(children):
            if not iterable(v) or id(v) in pathSeenIds:
                continue
            _keypath = (*keypath, k)
            _pathCount = (*pathCount, i)
            ret = yield from type(self)(
                v,
                maxDepth=maxDepth,
                cls=cls,
                getChild=getChild,
                readonly=readonly,
                setValue=setValue,
                pathSeenIds=pathSeenIds,
                forkGraph=forkGraph,
                keypath=_keypath,
                pathCount=_pathCount,
            )
            if isinstance(ret, cls):
                pk2cn: WeakValueDictionary[Any, CLS] = forkGraph.get(SELF)
                """parent key to child nodes"""
                if pk2cn is None:
                    pk2cn = WeakValueDictionary()
                    forkGraph[SELF] = pk2cn
                pk2cn[k] = ret
            if not readonly:
                # substitute python dict to sdict
                setValue(SELF, k, ret)  # self[k] = ret
        return SELF

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> CLS:
        ret = next(self._iter)
        if not self._iter_started:
            self._iter_started = True
        return ret

    def send(self, value):
        """```python
        gen.send(MY_NEW_NODE) # will set current node as `MY_NEW_NODE`
        gen.send(NONE) # will set to `None`
        gen.send(None) # won't set
        ```
        """
        return self._iter.send(value)

    @copy_args(Generator.throw)
    def throw(self, *args, **kw):
        return self._iter.throw(*args, **kw)

    @copy_args(Generator.close)
    def close(self):
        return self._iter.close()

    class _Kwargs(TypedDict, total=False):
        """maintained internally"""

        pathSeenIds: set[int]
        forkGraph: ForkGraph
        keypath: tuple
        pathCount: PathCount

    class Kwargs(_Kwargs, total=False):
        """need user explicity declare"""

        # obj: Node
        maxDepth: int | float
        cls: type[Self] | None
        getChild: "dfs.GetChildFunc"
        readonly: bool
        setValue: "dfs.SetValueFunc"


# ------------------------------------------------------------
# dictDict
# ------------------------------------------------------------


@dataclass
class ddYield[CLS = "sdict"]:
    """yield of dictDict()"""

    v: Any
    """per item(usually dict) of list"""
    self: CLS
    """you should use `if newKey in self` to prevent duplicate key, otherwise `update()` would **overwrite** old value"""


@dataclass
class ddReturn[CLS = "sdict"]:
    """return of dictDict()"""

    v: CLS
    """final result value"""
    keypaths: list[tuple]
    """which keypaths are converted into dict[dict] from list[dict]"""


class KwargsDictDict(TypedDict, total=False):
    value_of_idKey: Callable[[Any], Any]
    """value_of_idKey(current_dict): get merge-key of each item"""


def dictDict[CLS = "sdict"](
    gen_dfs: Iterator[CLS],
    value_of_idKey: Callable[[Any], Any] = id,
) -> Generator[ddYield[CLS], Hashable, ddReturn[CLS]]:
    """
    list[dict[list...]] or dict[list[dict...]] to pure nest dict like dict[dict[dict...]], by extract merge-key from each item
    use before `merge()`, because list[dict] is hard to merge correctly(while list[Scalar] or dict[...] is easy)

    ```python
    from functools import partial

    for sdic in dictDict(dfs(obj), value_of_idKey=partial(get_item, keys="id")):
        # will auto update {..., children: [{"id":123},...]} to {..., children: {123:{...}, ...}}
        # but if not found the "id", will raise KeyError

    for sdic in (dd := dictDict(dfs(obj))):
        if isinstance(sdic.v, MyType):
            dd.send("another-key")
        else:
            pass  # dd.send(None)
            # default fallback is `id(current_item)`
    ```

        Args:
        obj: dict or list, Map or Iterable
        value_of_idKey(current_dict): get merge-key of each item.
            For `dict["id"]`, use `partial(get_item, keys="id")`.

    Raises:
        KeyError: when `value_of_idKey()` tries to access a missing key like `"id"`
    """
    converted: list[sdict] = []

    def _yield(self: sdict, v):
        key = yield ddYield(v=v, self=self)
        if key is NONE:
            key = None
        elif key is None:
            key = value_of_idKey(v)
        self.update({key: v})
        # gen.send(self) # TODO: 似乎执不执行，结果都一样？

    # 必须等待dfs()消耗完后再开始覆写，因为每次dfs()迭代的内部都会把子节点写回父节点
    # {
    #   "g1": {...},
    #   "g2": {...},
    #   0: {...}, # dfs() 写回的旧key
    #   1: {...},
    # }
    nodes = tuple(gen_dfs)
    if not nodes:
        raise ValueError("gen_dfs is empty")
    root = cast(sdict, nodes[0])
    for self in nodes:
        Log.debug("self=%s", self)
        if not isinstance(self, sdict):
            raise TypeError("only support dictDict(gen= dfs(cls=sdict) )")
        if isinstance(self.v, Mapping) or not iterable(self.v):
            continue
        objs = tuple(self.v)
        self.use_ref = False
        self.ref = None
        for obj in objs:
            yield from _yield(self, obj)
        converted.append(self)
    try:
        root.rebuild()
    except Exception as e:
        Log.error(
            "sdict(root).rebuild() failed, which can't update the keypaths for each node",
            exc_info=e,
        )
    keypaths = [node.keypath for node in converted]
    Log.debug("final root=%s\nkeypaths=%s", root, keypaths)
    return ddReturn(v=root, keypaths=keypaths)


def un_dictDict[CLS = "sdict"](context: ddReturn[CLS]) -> CLS:
    """restore from dictDict()"""
    root = context.v
    # Restore deepest paths first so child paths like ("groups", "g1", "children")
    # still exist before their parent ("groups") is turned back into a list.
    for keypath in sorted(set(context.keypaths), key=len, reverse=True):
        current = get_item_attr(root, keypath, default=UNSET)
        if current is UNSET or not isinstance(current, Mapping):
            continue
        restored = list(current.values())
        if keypath:
            set_item_attr(root, keypath, restored)
        else:
            root = restored
    context.v = root
    return root


# ------------------------------------------------------------
# unref
# ------------------------------------------------------------


@overload
def unref[K, V](
    obj: Mapping[K, V], const=False, _memo: dict[int, Any] | None = None
) -> dict[K, V]: ...


@overload
def unref[V](
    obj: Iterable[V], const=False, _memo: dict[int, Any] | None = None
) -> list[V]: ...


def unref(obj, const=False, _memo: dict[int, Any] | None = None):
    """
    Args:
        const: return tuple/MappingProxyType if const else list/dict,
        _memo: just leave default, internal {id(): value}
    """
    if _memo is None:
        _memo = {}
    value = obj.v if isinstance(obj, sdict) else obj
    if not iterable(value):
        return value

    obj_id = id(value)
    if obj_id in _memo:
        return _memo[obj_id]

    if isinstance(value, Mapping):
        out = {}
        _memo[obj_id] = out
        for k, v in value.items():
            out[k] = unref(v, const=const, _memo=_memo)
        if const:
            frozen = MappingProxyType(out)
            _memo[obj_id] = frozen
            return frozen
        return out

    out_list = []
    _memo[obj_id] = out_list
    out_list.extend(unref(v, const=const, _memo=_memo) for v in value)
    if const:
        frozen = tuple(out_list)
        _memo[obj_id] = frozen
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

    ref = None
    deep = True
    pathCount = (0,)
    getChild: dfs.GetChildFunc = get_children

    class Kwargs(TypedDict, total=False):
        # data: Mapping[K, V] | None
        ref: R | None
        deep: bool
        forkGraph: ForkGraph[Any]
        pathCount: PathCount
        getChild: dfs.GetChildFunc

    def __init__(
        self,
        data: Mapping[K, V] | Iterable[tuple[K, V]] | Any | None = None,
        ref: R = ref,
        *,
        deep=True,
        forkGraph: ForkGraph[Any] | None = None,
        pathCount: PathCount = pathCount,
        getChild: dfs.GetChildFunc = getChild,
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
            getChild: used for __getitem__
        """
        if isinstance(data, sdict):
            Log.warning(
                "%s is sdict, use deepcopy(mySdict) or copy(mySdict) to keep internal states",
                type(data),
            )

        self.repr = False
        """if you want `{}`, set to False; if you want `sdict({})` truly raw data, set to True"""
        self.use_ref: bool = data is None
        """affect the return of self.v"""
        super().__init__(data or ())
        self.ref = ref
        """can storage pydantic_model_data, list_data..."""
        self.forkGraph = forkGraph if forkGraph is not None else WeakKeyDictionary()
        self.pathCount = pathCount
        self.getChild = getChild
        if deep:
            self.rebuild()

    def rebuild(self):
        """build index/cache entirely.\n
        currently I recommand re-init a sdict instance if you want to **treat a child as new root node**, by `sdict(myChild_as_NewRoot_oldSdict)`
        """
        self.forkGraph = WeakKeyDictionary()
        for _ in dfs(
            self,
            forkGraph=self.forkGraph,
            pathCount=self.pathCount,
            getChild=self.getChild,
        ):
            pass
        self.del_cache()

    _Type_Cached = Literal["keypath"]
    _cached = args_of_type(_Type_Cached)
    _cached_parent = ("keypath",)
    _cached_child = ()

    def del_cache(
        self,
        without: Iterable[_Type_Cached] = (),
        only: Iterable[_Type_Cached] | None = None,
    ):
        if only is None:
            todo = set(self._cached) - set(without)
        else:
            todo = only
        for attr in todo:
            try:
                delattr(self, attr)
            except AttributeError:
                pass

    def __init_subclass__(cls) -> None:
        cls._cached = args_of_type(cls._Type_Cached)

    @property
    def v(self) -> Self | R | Any:
        """
        return self.ref if self.use_ref\n
        will unpack weakref.ref
        """
        if not self.use_ref:
            return self
        elif isinstance(self.ref, ref):
            return self.ref()
        return self.ref

    def unref(self):
        """deep unref all `sdict.v`, used for `json.dumps(sd.unref)`"""
        return unref(self.v)

    @staticmethod
    def _is_keypath(key: Any) -> TypeIs[Sequence]:
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

    def __getitem__(self, key: K | Iterable[K] | slice):
        """
        - before rebuild(), return actual value
        - after rebuild(), return `sdict` that wraps actual value
        """
        if isinstance(key, slice):
            v = [x for x in self.values_flat(slice=key, digLeaf=False)]
        elif self.use_ref or self._is_keypath(key):
            # key is list / tuple
            v = self.getitem(key)
        else:
            # key = cast(K, key)
            v = super().__getitem__(key)
        return v

    def go(self, up: int = 2) -> Self:
        """`go(2)` == `.parent.parent`"""
        v = self
        if up >= 0:
            try:
                for _ in range(up):
                    if not v.parent:
                        break
                    v = v.parent
            except Exception as e:
                raise TypeError(f"Expected {type(self)=}, got {type(v)=}") from e
        else:
            # TODO: goto deepest leaf or just childKey[0].childKey[0]...?
            raise _TODO
        return v

    def setitem(self, key: Sequence[K], value, at=UNSET):
        """see `set_item_attr()`"""
        return set_item_attr(self.v if at is UNSET else at, key, value)

    def __setitem__(self, key: K | Sequence[K] | slice, value):
        if isinstance(key, slice):
            raise _TODO  # TODO: batch
            for i in self.keys_flat(slice=key):
                self[i] = value
        elif self.use_ref or self._is_keypath(key):
            self.setitem(key, value)
        else:
            super().__setitem__(key, value)
        self.del_cache(only=self._cached_child)

    def birth(self, key: K | Iterable[K], existOk: bool = True) -> Self:
        """access or create keypath's value if not existed. eg: `mkdir -p`"""

    def delitem(self, key: Sequence[K], at=UNSET):
        """see `del_item_attr()`"""
        return del_item_attr(self.v if at is UNSET else at, key)

    def __delitem__(self, key: K | Sequence[K] | slice):
        if isinstance(key, slice):
            raise _TODO  # TODO: batch
            for i in self.keys_flat(slice=key):
                del self[i]
        elif self.use_ref or self._is_keypath(key):
            self.delitem(key)
        else:
            super().__delitem__(key)
        self.del_cache(only=self._cached_child)

    def __del__(self):
        childkeys = self.__dict__.get("childkeys")
        if childkeys is None:
            return
        for child in childkeys:
            try:
                child.del_cache()
            except Exception:
                pass

    def __call__(self, *key, **kw) -> Self:
        """
        `__call__` may undergo **breaking changes** in the future, based on its most common calling patterns and usage scenarios.
        ```python

        ```
        """
        raise _TODO

    def __hash__(self):
        return id(self)

    # def __eq__(self, value: object) -> bool:
    #     if isinstance(value, type(self)):
    #         return self.v == value.v
    #     return self.v == value

    def __repr__(self) -> str:
        r = super().__repr__()
        return r if self.repr else r[len(type(self).__name__) + 1 : -1] or "{}"

    @copy_args(OrderedDict.__ior__)
    def __ior__(self, value):
        if not value:
            return self
        super().__ior__(value)
        self.del_cache(only=self._cached_child)
        return self

    @copy_args(OrderedDict.pop)
    def pop(self, key):
        super().pop(key)
        self.del_cache(only=self._cached_child)

    @copy_args(OrderedDict.popitem)
    def popitem(self, last):
        super().popitem(last)
        self.del_cache(only=self._cached_child)

    @copy_args(OrderedDict.update)
    def update(self, m):
        if not m:
            return
        super().update(m)
        self.del_cache(only=self._cached_child)

    @copy_args(OrderedDict.clear)
    def clear(self):
        super().clear()
        self.del_cache(only=self._cached_child)

    # TODO: move_to_end, 暂时不做

    @classmethod
    def _are_equal(cls, a, b):
        """also compare the **order of keys** or `self.v`, because python's `==` will ignore that"""
        return are_equal(a, b, preprocess=lambda x: x.v if isinstance(x, sdict) else x)

    def equal(self, obj):
        """also compare the **order of keys** or `self.v`, because python's `==` will ignore that"""
        return self._are_equal(self, obj)

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

            if isinstance(parent, type(self)):
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
            edge = next(self._parentWithKey, None)
            if edge is None:
                raise KeyError(new, "not found")
            parent, old = edge
            if not isinstance(parent, MutableMapping):
                raise TypeError(f"parent must be MutableMapping, got {type(parent)!r}")
            if old not in parent:
                raise KeyError(old, "not found")
            if _can_rename(parent):
                changed = _rename_one(parent, old, new)
            if changed:
                self.del_cache(only=self._cached_parent)
            return self

        if not deep:
            if old not in self:
                raise KeyError(old, "not found")
            if _can_rename(self):
                changed = _rename_one(self, old, new)
            if changed:
                self.del_cache(only=self._cached_parent)
            return self

        for parent in self.dfs():
            if not (old in parent and _can_rename(parent)):
                continue
            changed = _rename_one(parent, old, new) or changed
        if changed:
            self.del_cache(only=self._cached_parent)  # TODO: need test
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
                self.del_cache(only=self._cached_parent)
            return self

        for parent in self.dfs():
            if _rename_plan(parent):
                changed = _rename_parent(parent) or changed
        if changed:
            self.del_cache(only=self._cached_parent)
        return self

    def merge(
        self,
        obj: Mapping,
        **kwargs: Unpack["_merge.Kwargs"],
    ) -> Self:
        """
        Merge `obj` into `self` in place.

        Args:
            obj: the newer mapping to merge into current `self`
            **kwargs: forwarded to `jsonc_sdict.merge.merge`, except `old_new`
        """
        if "old_new" in kwargs:
            raise ValueError("sdict.merge() got unexpected keyword argument 'old_new'")
        from jsonc_sdict.Merge import merge

        merge((self, obj), **kwargs).solve_all()
        return self

    def keys_flat(
        self,
        withParents: bool = False,
        digLeaf=True,
        digList=True,
        slice: slice = slice(None),
        **kwargs: Unpack[dfs.Kwargs],
    ) -> Generator[tuple, Never, None]:
        """
        like benedict.keypaths(). See items_flat() for else args.
        Args:
            digLeaf: default False. if True, the result's of {a:{b:1}} will be `(a,b)` instead of `(a,)`
            **kwargs: passed to `dfs()`
        """
        kw = dict(
            withParents=withParents,
            digLeaf=digLeaf,
            digList=digList,
            slice=slice,
        )
        kw.update(kwargs)  # type: ignore
        for k, _ in self.items_flat(**kw):
            yield k

    def values_flat(
        self,
        withParents: bool = False,
        digLeaf=True,
        digList=True,
        slice: slice = slice(None),
        **kwargs: Unpack[dfs.Kwargs],
    ) -> Generator[Self, Never, None]:
        """
        See items_flat() for else args.
        Args:
            digLeaf: default False. if True, the result's of {a:{b:1}} will be `1` instead of `{b:1}`
            **kwargs: passed to `dfs()`
        """
        kw = dict(
            withParents=withParents,
            digLeaf=digLeaf,
            digList=digList,
            slice=slice,
        )
        kw.update(kwargs)  # type: ignore
        for _, v in self.items_flat(**kw):
            yield v

    @overload
    def items_flat(
        self,
        withParents: bool = False,
        digLeaf: Literal[True] = True,
        digList: bool = True,
        slice: slice = slice(None),
        **kwargs: Unpack[dfs.Kwargs],
    ) -> Generator[tuple[tuple, Any], Any, None]: ...

    @overload
    def items_flat(
        self,
        withParents: bool = False,
        digLeaf: Literal[False] = False,
        digList: bool = True,
        slice: slice = slice(None),
        **kwargs: Unpack[dfs.Kwargs],
    ) -> Generator[tuple[tuple, Self], Any, None]: ...

    def items_flat(
        self,
        withParents: bool = False,
        digLeaf: bool = True,
        digList: bool = True,
        slice: slice = slice(None),
        **kwargs: Unpack[dfs.Kwargs],
    ) -> Generator[tuple[tuple, Self], Any, None]:
        """
        Args:
            withParents: Defaults to False, so only the deepest leaf nodes are yielded. If True, parent nodes at each level are yielded as well.
            digLeaf: if True, the result's of {a:{b:1}} will be `(a,b),1` instead of `(a),{b:1}`
            digList: set False if you only want dict-dict-dict, instead of dict-list-dict...
            slice: depth filter relative to the deepest depth in the current traversal result.
            **kwargs: passed to `dfs()`
        """
        getChild = kwargs.get("getChild", get_children)
        if digList is False:
            getChild = get_children_noList
        kw = dict(readonly=True)
        kw.update(kwargs)  # type: ignore
        gen_dfs = self.dfs(**kw)
        nodes = tuple(gen_dfs)

        # NOTE: this is more correct than self.deepest.depth.
        total = max((node.depth for node in nodes), default=-1) + 1
        for node in nodes:
            if (
                isinstance(node, type(self))
                and in_range(node.depth, slice, total=total)
                and (withParents or isFlatIterable(node.v))
            ):
                if digLeaf:
                    gen_leaf = (
                        ((*node.keypath, k), v) for k, v in getChild(node, node.v)
                    )
                else:
                    gen_leaf = ((node.keypath, node),)

                for kp, v in gen_leaf:
                    # NOTE: v =  scale_value(int/str...) if digLeaf else container_at_leaf(dict/list...)
                    NEW = yield kp, v
                    if NEW is not None:
                        if NEW is NONE:
                            NEW = None
                        self[node.keypath] = NEW

    @property
    def leaves(self) -> Generator[tuple[tuple, Self], Any, None]:
        return self.items_flat(digLeaf=False)

    def dfs(
        self,
        maxDepth=float("inf"),
        getChild: dfs.GetChildFunc = get_children,
        readonly=False,
        setValue=set_item_attr,
        **kwargs: Unpack[dfs._Kwargs],
    ) -> dfs[K, V, Self]:
        """see `dfs(**kwargs)`"""
        pathCount = (*self.pathCount[:-1], max(self.pathCount[-1] - 1, 0))
        kw = dict(
            cls=type(self),
            maxDepth=maxDepth,
            getChild=getChild,
            readonly=readonly,
            setValue=setValue,
            forkGraph=self.forkGraph,
            keypath=self.keypath,
            pathCount=pathCount,
        )
        kw.update(kwargs)
        return dfs(obj=self.v, **kw)

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
        self.del_cache(only=self._cached_child)

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
    def _upstreamPaths(self) -> Generator[NodeKeyDict[Any, Self], Never, None]:
        """Enumerate all root-to-self paths derived from `self.forkGraph`."""
        # TODO: cycleStart
        yield from all_path(self.forkGraph, target=self)

    @property
    def keypaths(self) -> Generator[tuple, Never, None]:
        """upstream from root. Use this when shared objects create multiple paths to the same node."""
        return (nk.keypath for nk in self._upstreamPaths)

    # NOTE: 需要重新赋值的才用 @cached_property
    @cached_property
    def keypath(self) -> tuple:
        """of the current iteration. This is unstable for shared nodes; use `.keypaths` in that case."""
        return next(self.keypaths)

    @property
    def nodePaths(self) -> Generator[Iterator[Self], Never, None]:
        """upstream from root. Use this when shared objects create multiple paths to the same node."""
        return (nk.nodePath for nk in self._upstreamPaths)

    @property
    def nodePath(self) -> Iterator[Self]:
        """This is unstable for shared nodes; use `.keypaths` in that case."""
        return next(self.nodePaths)

    @property
    def _parentWithKey(self) -> Generator[tuple[Self, Any], Never, None]:
        """yield `(parent, key_in_parent)` from parent level."""
        for parent, children in self.forkGraph.items():
            for key, child in children.items():
                if child is self:
                    yield parent, key

    @property
    def parents(self) -> Generator[Self, Never, None]:
        seenIds: set[int] = set()
        for parent, _ in self._parentWithKey:
            id_parent = id(parent)
            if id_parent in seenIds:
                continue
            seenIds.add(id_parent)
            yield parent

    @property
    def parent(self) -> Self | None:
        """This is unstable for shared nodes; use `.parents` in that case."""
        return next(self.parents, None)

    @property
    def roots(self) -> Generator[Self, Never, None]:
        seenIds: set[int] = set()
        for nodePath in self.nodePaths:
            root = next(nodePath, self)
            id_root = id(root)
            if id_root in seenIds:
                continue
            seenIds.add(id_root)
            yield root

    @property
    def root(self) -> Self:
        return next(self.roots)

    @property
    def depth(self):
        """from root"""
        return len(self.keypath)  # len(self.pathCount)

    @property
    def deepests(self) -> list[Self]:
        deepests: list[Self] = []
        seenIds: set[int] = set()
        max_depth = -1

        def _has_descendable_child(node: Self) -> bool:
            path_ids = {id(n) for n in node.nodePath}
            for _, child in get_children(node, node.v):
                if iterable(child) and id(child) not in path_ids:
                    return True
            return False

        for node in self.dfs():
            if _has_descendable_child(node):
                continue
            node_id = id(node)
            if node.depth > max_depth:
                max_depth = node.depth
                deepests = [node]
                seenIds = {node_id}
            elif node.depth == max_depth and node_id not in seenIds:
                deepests.append(node)
                seenIds.add(node_id)
        return deepests

    @property
    def deepest(self) -> Self:
        """deepest leaf node"""
        return self.deepests[0]

    @property
    def height(self):
        """from leaves"""
        return max((node.depth for node in self.values_flat(digLeaf=False)), default=0)

    @property
    def childkeys(self):
        """`del sdict.childkeys` to refresh cache"""
        return tuple(dfs(self.v, maxDepth=1))  # TODO: 逻辑不对
