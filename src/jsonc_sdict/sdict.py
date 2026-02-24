"""
because list is not hashable, so list is designed for:
- don't treat like key name: see `type Key`
"""

from collections import UserDict
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from functools import cached_property
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
        obj: need support nested `__getitem__()`, or raise `TypeError`
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


def iterable[V](obj: Iterable[V] | Any) -> TypeGuard[Iterable[V]]:
    """Iterable but NOT str, bytes"""
    return isinstance(obj, Iterable) and not isinstance(obj, (str, bytes))


def dfs[K = int, V = Any](
    obj: Node[K, V],
    maxDepth=float("inf"),
    List=True,
    *,
    parent: WeakList["sdict"] = WeakList(),
    keypath: KeyPaths = (),
    pathCount: PathCount = (0,),
):
    """
    do NOT update scaned/yielded data while iterating.
    Args:
        maxDepth: deepest of dfs, stop digging if deeper
        parent: 只能存储强引用

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
    if not (obj and iterable(obj) and len(keypath) <= maxDepth):
        return obj

    pathCount = (*pathCount[:-1], pathCount[-1] + 1)
    if isinstance(obj, sdict):
        # update
        obj.parent = parent
        obj.keypath = keypath
        obj.pathCount = pathCount
        self = obj
    elif isinstance(obj, Mapping):
        self = sdict(
            obj,
            # deep==True等价于执行dfs()，所以False即可
            deep=False,
            parent=parent,
            keypath=keypath,
            pathCount=pathCount,
        )
    elif List:
        self = sdict(
            ref=obj, deep=False, parent=parent, keypath=keypath, pathCount=pathCount
        )
    yield self
    children = (
        (k, v)
        for k, v in (obj.items() if isinstance(obj, Mapping) else enumerate(obj))
        if iterable(v) and (List or isinstance(v, Mapping))
    )
    for k, v in children:
        ret = yield from dfs(
            v,
            maxDepth=maxDepth,
            List=List,
            parent=WeakList((self,)),
            keypath=(*keypath, [k]),
            pathCount=pathCount,
        )
        self[k] = ret
    return obj


class sdict[K = str, V = Any, R = Any, KP = Any](UserDict[K, V]):
    """
    signal dict, or "dict design for json in actual business", like benedict, but less limitation, more useful context, more strict type hint.

    Generic 泛型:
        K,V: the current depth that Key,Value's type \n
            当前层级的 Key, Value 键值类型
        KK: Type possibilities for all nested depths\n
            所有嵌套层的类型可能性
    """

    type IterAsMap = Iterable[tuple[K, V]] | Iterable[Iterable[K | V]]

    def __init__(
        self,
        data: Mapping[K, V] | IterAsMap | None = None,
        ref: R | None = None,
        *,
        deep=True,
        parent: WeakList[V] = WeakList(),
        keypath: KeyPaths[KP, Any] = (),
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
        self.data = dict(
            dfs(
                self.data,
                parent=self.parent,
                keypath=self.keypath,
                pathCount=self.pathCount,
            )
        )
        try:
            # rebuild cache
            del self.childkeys
        except AttributeError:
            pass

    def getitem(self, key: Iterable[K]):
        """override this func when you want to `getAttr()`, by default only get_item()"""
        return get_item(self.data, key, noRaise=())

    def __getitem__(self, key: K | Iterable[K] | slice[int | None] | Any):
        if iterable(key) and not isinstance(key, Mapping):
            v = self.getitem(key)
        elif isinstance(key, slice):
            v = list(self.values_flat(key))
        else:
            key = cast(K, key)
            v = super().__getitem__(key)
        return (
            sdict(v, deep=False)
            if not isinstance(v, sdict) and isinstance(v, Mapping)
            else v
        )

    def __hash__(self):
        return id(self)

    def keys_flat(self, slice: slice[int | None] = slice(None), List=True):
        """like benedict.keypaths()"""
        for K, _ in self.items_flat(slice=slice, List=List):
            yield K

    def values_flat(self, slice: slice[int | None] = slice(None), List=True):
        for _, v in self.items_flat(slice=slice, List=List):
            yield v

    def items_flat(self, slice: slice[int | None] = slice(None), List=True):
        # https://github.com/python/cpython/issues/87122#issuecomment-1828385975
        for _, v in dfs(self.data, List=List):
            if isinstance(v, sdict) and in_range(v.depth, slice):
                yield v.keypath, v

    @property
    def depth(self):
        """from root"""
        return len(self.keypath)  # len(self.pathCount)

    @cached_property
    def height(self):
        """from leaves"""

    @cached_property
    def childkeys(self):
        """`del sdict.childkeys` to refresh cache"""
        return tuple(dfs(self.data, maxDepth=1))

    def children_filter(self):
        return dfs(self.data)


def test():
    # 测试用例1：基础嵌套结构
    d1 = sdict((("k", 1),))
    print(f"{d1=}")
    assert d1["k"] == 1, "基础嵌套取值失败"

    # 测试用例2：模拟业务场景的多层嵌套（目标格式：d2['user','info','address','areas',0,'district']）
    d2 = sdict(
        {
            "user": {
                "info": {
                    "name": "张三",
                    "age": 28,
                    "address": {
                        "province": "广东省",
                        "city": "深圳市",
                        "areas": [
                            {"district": "南山区", "street": "科技园路"},
                            {"district": "宝安区", "street": "新安路"},
                        ],
                    },
                },
                "settings": {"theme": "dark", "lang": "zh-CN"},
            }
        }
    )
    # 核心测试：多层嵌套 + 列表索引
    district_val = d2["user", "info", "address", "areas", 0, "district"]
    print(f"{d2['user', 'info', 'address', 'areas', 0, 'district']=}")  # 输出 南山区
    assert district_val == "南山区", "业务场景嵌套取值失败"

    print(f"{list(d2.items_flat())=}")

    # 测试用例3：异常场景（无noRaise时抛异常）
    print("\n=== 异常场景测试 ===")
    try:
        d2["user", "info", "address", "areas", 99, "district"]  # 索引99不存在
    except IndexError as e:
        print(f"预期异常（IndexError）: {e}")

    try:
        d2["user", "info", "address", "xxx", 0, "district"]  # key xxx不存在
    except KeyError as e:
        print(f"预期异常（KeyError）: {e}")

    print("\n所有测试用例执行完成 ✅")


if __name__ == "__main__":
    test()
