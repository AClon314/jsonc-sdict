"""
merge & solver
"""

from dataclasses import dataclass, asdict
from functools import cached_property
from types import MappingProxyType
from typing import (
    cast,
    overload,
    runtime_checkable,
    Any,
    Self,
    Final,
    Union,
    Unpack,
    TypeIs,
    Literal,
    Callable,
    Protocol,
    FrozenSet,
)

from collections.abc import (
    Mapping,
    Iterable,
    Generator,
    MutableMapping,
    MutableSequence,
    MutableSet,
)

from deepdiff import DeepDiff as _DeepDiff
from deepdiff.diff import DeepDiffProtocol as _DeepDiffProtocol
from deepdiff.operator import BaseOperator
from deepdiff.helper import NotPresent
from deepdiff.model import DiffLevel

from jsonc_sdict.share import (
    PS,
    TV,
    NONE,
    _TODO,
    RAISE,
    UNSET,
    iterable,
    getLogger,
    return_of,
    isFlatIterable,
)
from jsonc_sdict.sdict import (
    dfs,
    dictDict,
    get_item_attr,
    set_item_attr,
    del_item_attr,
    KwargsDictDict as SdictKwargsDictDict,
)

Log = getLogger(__name__)

MergeOrderBase = Literal[
    "^",
    "old",
    "new",
    "old-^",
    "new-^",
]
MergeOrder = Literal[
    "",
    "^",
    "old",
    "new",
    "old-^",
    "new-^",
    "old,new-^",
    "new,old-^",
    "old-^,new",
    "old-^,new-^",
    "new-^,old",
    "new-^,old-^",
    "old-^,new-^,^",
    "old-^,^,new-^",
    "new-^,old-^,^",
    "new-^,^,old-^",
    "^,old-^,new-^",
    "^,new-^,old-^",
]
# merge_orders = get_args(MergeOrder)
# merge_order_bases = get_args(MergeOrderBase)

type Type_MergeEnd = Literal["old", "new", "del"]
type IsType[T, *TS] = type[T] | tuple[*TS] | Callable[[Any], bool]
"""dict | (dict,) | lambda obj: isinstance(obj, dict)"""


@overload
def isType[T](obj, types: type[T]) -> TypeIs[T]: ...


# https://github.com/python/mypy/issues/16720
@overload
def isType[*T](obj, types: tuple[*T]) -> TypeIs[Union[*T]]: ...  # type: ignore


@overload
def isType(obj, types: Callable[[Any], bool]) -> bool: ...


def isType(obj, types: IsType) -> bool:
    """if callable, then need manually `obj=cast(type, obj)`"""
    return isinstance(obj, types) if isinstance(types, (type, tuple)) else types(obj)


def isNotPresent(obj):
    return isinstance(obj, NotPresent)


type Type_DiffReport = Literal[
    "values_changed",
    "type_changes",  # 类型改变
    "dictionary_item_added",  # 字典项添加
    "dictionary_item_removed",
    "iterable_item_added",  # 可迭代项添加
    "iterable_item_removed",
    "repetition_change",  # 重复项变化（使用 report_repetition=True 时）
    "attribute_added",  # 属性添加（对象比较时）
    "attribute_removed",
    "set_item_added",  # 集合项添加
    "set_item_removed",
]


class DeepDiff[T1, T2 = T1](_DeepDiff):
    t1: T1
    t2: T2
    up: Self
    """parent"""
    down: Self
    path: Callable

    @cached_property
    def keypath(self) -> tuple:
        return tuple(self.path(output_format="list"))  # type: ignore


@runtime_checkable
class DeepDiffProtocol(_DeepDiffProtocol, Protocol): ...


class merge[T1, T2](Iterable):
    """
    ## Developer says
    - `root` would always the latest data, `node` would always the initial data.
    - 🎃 Issue/Pull Request welcome! share your solver! 👻 \n
    创建Issue或PR来分享你的预设，帮助大家节省时间!
    """

    _Type_AutoDict = dict[IsType, MergeOrder | Type_MergeEnd]
    """`{dict: "del", (mergeable_type, sdict): "", lambda obj:isinstance(obj,Sequence) and not isinstance(obj,(str,bytes)): "old"}`"""

    root: DeepDiff
    """newest/latest root data"""
    node: DeepDiff
    """initial/original node data. use `old`/`new` instead of `node.t1`/`node.t2` if you want to get the current value"""
    env: "Env"

    auto_old_new: _Type_AutoDict = {iterable: "old,new-^"}
    auto_new_old: _Type_AutoDict = {iterable: "new,old-^"}

    def _inject_args(func: Callable[PS, TV]) -> Callable[PS, TV]:

        def wrapper(
            self: Self,
            root: DeepDiff | None = None,
            node: DeepDiff | None = None,
            *args: PS.args,
            **kwargs: PS.kwargs,
        ) -> TV:
            func_name = cast(str, func.__name__)
            is_solver = func_name.startswith("solver_")
            # Log.debug(f"{func.__name__=}\t{root=}\t{node=}\t\t{args=}")
            if is_solver and not self._iter_started:
                next(self)
            if root is None:
                root = self.root
            if node is None:
                node = self.node
            kw = {**asdict(self.env), **kwargs}
            return func(self, root, node, *args, **kw)  # type: ignore

        return wrapper  # type: ignore

    @property
    def old(self) -> Any:
        """newest/latest node.t1 data"""
        return self.get_item()

    @property
    def new(self) -> Any:
        """newest/latest node.t2 data"""
        return self.get_item(self.root.t2)

    @property
    def merged(self) -> T1:
        """result from root.t1"""
        return self.root.t1

    @dataclass
    class Env:
        auto: Final["merge._Type_AutoDict"]
        skdv: Type_MergeEnd
        """sameKey_diffValue"""
        ddPaths: Final[set[tuple]]
        """dictDict() converted paths"""
        ddRestore: bool
        """default True, set to False to keep dictDict without restore step."""
        diffType: Type_DiffReport | None = None

    @_inject_args
    def get_item[D](
        self,
        root: Any | None = None,
        node: DeepDiff | None = None,
        default: D | RAISE = RAISE,
        noRaise=(
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
        ),
        **env,
    ) -> Any | D:
        """
        Args:
            root: `root.t1`/`root.t2`. if `root` then fallback to `root.t1`(old)
        """
        assert root is not None
        assert node is not None
        if isinstance(root, DeepDiffProtocol):
            root = root.t1
        return get_item_attr(root, node.keypath, default=default, noRaise=noRaise)

    @_inject_args
    def set_item(
        self,
        root: DeepDiff | None = None,
        node: DeepDiff | None = None,
        value=UNSET,
        **env,
    ):
        """
        Args:
            value: by default use `t2`(new)
        """
        assert root is not None
        assert node is not None
        if value is NONE:
            value = None
        elif value is UNSET:
            value = self.get_item(root.t2, node)
        return set_item_attr(root.t1, node.keypath, value)

    @_inject_args
    def del_item(
        self, root: DeepDiff | None = None, node: DeepDiff | None = None, **env
    ):
        """
        Args:
            root: `root.t1`/`root.t2`. if `root` then fallback to `root.t1`(old)
        """
        assert root is not None
        assert node is not None
        if isinstance(root, DeepDiffProtocol):
            root = root.t1
        return del_item_attr(root, node.keypath)

    @_inject_args
    def solver_keepInitClass(
        self, root: DeepDiff | None = None, node: DeepDiff | None = None, **env
    ) -> Self:
        """`node.t1.__class__(self.get_item(root, node))`, the initClass should accepct data as first positional arg"""
        assert root is not None
        assert node is not None
        Cls = node.t1.__class__
        now = self.get_item(root, node)
        self.set_item(root, node, Cls(now))
        return self

    @_inject_args
    def solver_keepImmutable(
        self, root: DeepDiff | None = None, node: DeepDiff | None = None, **env
    ) -> Self:
        """by default, keep old's immutable types wherever it appears."""
        assert root is not None
        assert node is not None
        init = node.t1
        now = self.get_item(root, node)
        if isinstance(init, tuple):
            v = tuple(now)
        elif isinstance(init, MappingProxyType):
            v = MappingProxyType(now)
        elif isinstance(init, FrozenSet):
            v = frozenset(now)
        self.set_item(root, node, v)
        return self

    @_inject_args
    def solver_forceImmutable(
        self, root: DeepDiff | None = None, node: DeepDiff | None = None, **env
    ) -> Self:
        """keep old's all immutable."""
        now = self.get_item(root, node)
        if isinstance(now, MutableSequence):
            v = tuple(now)
        elif isinstance(now, MutableMapping):
            v = MappingProxyType(now)
        elif isinstance(now, MutableSet):
            v = frozenset(now)
        self.set_item(root, node, v)
        return self

    @_inject_args
    def solver_sameKey_diffValue(
        self,
        root: DeepDiff | None = None,
        node: DeepDiff | None = None,
        *,
        skdv: Type_MergeEnd | None = None,
        diffType: Type_DiffReport | None = None,
        **env,
    ) -> None | Self:
        """
        Resolve **unmergeable** conflicts before applying `auto` rules. \n
        eg: old={"same": 1}, new={"same": 2} or new={"same": "1"} or new={"same": [...]}
        eg-both_container-but_type_mismatch: old={"same": [...]}, new={"same": {...}}
        But these would **NOT** apply `sameKey_diffValue` rule, they directly apply `auto` rule:
        eg-allList: old={"same": [...]}, new={"same": [...]}
        eg-allDict: old={"same": {...}}, new={"same": {...}}
        """
        assert root is not None
        assert node is not None
        assert diffType is not None

        t1 = node.t1
        if not (isinstance(t1, Mapping) and isinstance(t1, Mapping)):
            return  # it's not hurt, no need to raise
        if diffType == "values_changed":
            Log.debug(
                "deepdiff don't handle dict, so give up and next solver(usually `solver_auto`)"
            )
            return
        elif skdv == "del":
            self.del_item(root, node)
        elif skdv == "old":
            pass
        elif skdv == "new":
            self.set_item(root, node)
        return self

    @_inject_args
    def solver_intersect(
        self,
        root: DeepDiff | None = None,
        node: DeepDiff | None = None,
        *,
        order: MergeOrder | None = None,
        **env,
    ) -> Self:
        """
        - deepdiff report "values_changed" while dictA has **no intersection** with dictB.
        - `merged` result will **degrade** to basic types: list or dict. If you want to keep initial/original type, use `solver_keepInitClass` or `solver_keepImmutable`.
        """
        assert root is not None
        assert node is not None
        assert order is not None
        old = self.get_item(root.t1, node)
        new = self.get_item(root.t2, node)
        isOldMap = isinstance(old, Mapping)
        all_iterable = iterable(old) and iterable(new)
        xor_map = isOldMap ^ isinstance(new, Mapping)
        if not all_iterable or xor_map:
            raise ValueError(
                "old&new are not same type. Try to use `solver_sameKey_diffValue()` before, or override/try...catch"
            )
        Log.debug(f"🌒 intersect {type(old)=}\t{type(new)=}")
        orders = cast(list[MergeOrderBase], order.split(","))
        if isOldMap:
            # only use key not value, so you must use `sameKey_diffValue()` to solve conflict before!
            pos_old = orders.index("old") if "old" in orders else float("inf")
            pos_new = orders.index("new") if "new" in orders else float("inf")
            merged_map = {**old, **new} if pos_old < pos_new else {**new, **old}
            old = tuple(old)
            new = tuple(new)

        merged = []

        def update(s):
            merged.extend(s)

        if "^" in order:
            o = set(old)
            n = set(new)
            intersect = o.intersection(n)
        for od in orders:
            if od == "^":
                item = tuple(intersect)
            elif od == "old-^":
                item = tuple(o - intersect)
            elif od == "new-^":
                item = tuple(n - intersect)
            elif od == "old":
                item = old
            elif od == "new":
                item = new
            else:
                raise ValueError(f"invalid syntax={od} from {order=}")
            Log.debug("\t➕ item=%s from od=%s", item, od)
            update(item)
        if isOldMap:
            merged = dict({k: merged_map.get(k) for k in merged})
        Log.debug("🌒 old=%s\tnew=%s\tret=%s", old, new, merged)
        self.set_item(root, node, merged)
        return self

    @_inject_args
    def solver_auto(
        self,
        root: DeepDiff | None = None,
        node: DeepDiff | None = None,
        *,
        auto: _Type_AutoDict | None = None,
        diffType: Type_DiffReport | None = None,
        **env,
    ) -> Self:
        """auto merge"""
        assert root is not None
        assert node is not None
        if auto is None:
            auto = self.env.auto
        if diffType is None:
            diffType = self.env.diffType
        if diffType is None:
            raise ValueError("need `diffType` keyword arg")

        undef_t1 = isNotPresent(node.t1)
        undef_t2 = isNotPresent(node.t2)
        if undef_t1 and undef_t2:
            raise ValueError("node.t1 and node.t2 both NotPresent")
        hit = False
        if auto and not hit:
            _node = node
            if diffType.endswith("_added"):
                # d.keypath=['k'] <class 'deepdiff.helper.NotPresent'> d.t1=not present   <class 'str'> d.t2='v'
                keypath = _node.keypath
                _node = _node.up
                _node.keypath = keypath[:-1]
            for types, order in auto.items():
                hit_t1 = isType(_node.t1, types)
                hit_t2 = isType(_node.t2, types)
                if hit := (hit_t1 or hit_t2):
                    # 命中rule
                    Log.debug("⚽ hit auto types=%s", types)
                    break
        if not hit:
            raise ValueError(
                f"Not hit any auto rule, try...catch manually, or enhance your {auto=} for this data={node}"
            )
        if order == "del":
            self.del_item(root, node)
        elif order == "":
            # empty container
            self.set_item(root, node, node.t1.__class__())
        elif order == "old":
            pass
        elif order == "new" or (undef_t1 and "new" in order):  # type: ignore
            self.set_item(root, node)
        elif "^" in order:  # type: ignore
            self.solver_intersect(root, node, order=order)
        else:
            raise ValueError(f"invalid {{{types}:{order}}} from {auto=}")
        return self

    def solve(self) -> Self:
        """the default solver, `merged` result will **degrade** to basic types: list or dict."""
        if not self._iter_started:
            try:
                next(self)
            except StopIteration:
                return self
        if self.env.diffType == "values_changed":
            self.solver_sameKey_diffValue()
        elif self.env.diffType == "type_changes":
            raise TypeError("""We raise this error to remind you that you need to handle the "type_changes" case manually:
1. If you want your class to be merged correctly, it must be recognized as one of the following types: Mapping (dict), Sequence (list), or Set.
   For details, see `merge.deepdiff_args["ignore_type_in_groups"] = ((MutableMapping, MyObjType), ...)` and refer to the DeepDiff documentation (recommended to consult context7).
2. If you do NOT want merging and prefer to overwrite directly with either the new or old value, you can write it like this:
```python
for gen in merge(...):
    if gen.env.diffType == "type_changes":
        gen.solver_sameKey_diffValue(skdv="new") # directly use new value
    else:
        gen.solvers_XXX()
```""")
        elif self.env.diffType == "repetition_change":
            raise _TODO
        self.solver_auto()
        return self

    class MergeFlatIterableOperator(BaseOperator):
        """do NOT dig down when the iterable(or list/dict) is ALL consist of scalar values(bool|int|str|...). eg: [0,1,"s"], {"num": 0, "key": "s"}"""

        def match(self, level):
            # will still dig into [0, [...], 1]
            return isFlatIterable(level.t1) and isFlatIterable(level.t2)

        def give_up_diffing(self, level, diff_instance):
            if level.t1 != level.t2:
                diff_instance.custom_report_result(
                    "values_changed",
                    level,
                    {"old_value": level.t1, "new_value": level.t2},
                )
            return True  # 阻止继续往下按索引 diff

    deepdiff_args = dict(
        view="tree",
        ignore_type_in_groups=((MutableMapping,), (MutableSequence,), (MutableSet,)),
        custom_operators=(MergeFlatIterableOperator(),),
    )
    """
    see [DeepDiff](https://zepworks.com/deepdiff/current/ignore_types_or_values.html#ignore-type-in-groups), by default will:
    - tree view for raw data
    - ignore mostly `type_changes` to focus on data changes.
    - don't dig into list/dict at leaf level, be ready for merge list.
    """

    @staticmethod
    def _dictDict(
        old, new, **kw: Unpack[SdictKwargsDictDict]
    ) -> tuple[Any, Any, set[tuple]]:
        """
        NOTE: it's not a solver_func() because this should done **before** `DeepDiff()`

        Returns:
            old
            new
            ddPaths: which list[dict] paths are converted into dict[dict].
        """
        dd_old = return_of(dictDict(dfs(old), **kw))
        dd_new = return_of(dictDict(dfs(new), **kw))
        path = set((*dd_old.keypaths, *dd_new.keypaths))
        Log.debug("path=%s\nold=%s\nnew=%s", path, dd_old, dd_new)
        return dd_old.v, dd_new.v, path

    class _KwargsDictDict(SdictKwargsDictDict, total=False):
        restore: bool

    def __init__(
        self,
        old_new: tuple[T1, T2] | DeepDiff[T1, T2],
        dictDict: _KwargsDictDict | None = {},
        deepdiff_args: Mapping[str, Any] = deepdiff_args,
        sameKey_diffValue: Type_MergeEnd = "old",
        auto: _Type_AutoDict | None = auto_old_new,
        env={},
    ) -> None:
        """
        if new is dict or Map, will auto convert into DeepDiff internally.
        *inspired by [deepmerge](https://github.com/toumorokoshi/deepmerge) & [deepdiff](https://github.com/seperman/deepdiff) with [this issue](https://github.com/seperman/deepdiff/issues/552)*

        Usage:
        ```python
        for _ in (self := merge((old, new))):
            NEW = self.new + "you can manually solve each conflict"
            self.set_item(value=NEW)
        result = self.merged

        # or just use default solver to get merged result
        result = merge((old,new)).solve().merged
        ```

        Args:
            old_new: also accepct DeepDiff(t1, t2, \\*\\*merge.deepdiff_args) \n
                will overwrite the `old`, but you can use `old2 = deepcopy(old)` and pass like `old_new=(old2, new)`, see [Destructive Merge](https://deepmerge.readthedocs.io/en/latest/guide.html#merges-are-destructive)
            dictDict: suggest `{"idKey": "id"}`. convert `list[dict]` into `dict[dict]` with `idKey` internally, set to `None` to disable `dictDict()` pre-process. \n
                because list[dict] is hard to merge correctly(while dict or list[int|bool|str...basic_type_not_container] is easy) \n
                disabled when `old_new` is already DeepDiff, because dictDict() should run before DeepDiff()
            deepdiff_args: the kwargs to init DeepDiff(\\*\\*deepdiff_args), disabled when `old_new` is already DeepDiff
            sameKey_diffValue: default `"old"`, resolve **un**mergeable conflicts, see `solver_sameKey_diffValue()`
            auto: auto resolve **mergeable** conflict
                - if not match any rule at last, `gen.solver_auto()` will yield.
                    If do nothing or call `gen.send(None)`, will preserve **old**'s key-value pair.
                - `""` means {"preserve key & value container, but no values": []}
                - "del" means {}, del key-value pair.
                - `"old,new-^"` means, `old` with **intersection as ^** are **in front of** `new` without intersection.
                - `"new"` means only new, no old.
                - `"new-^,^,old-^"` means new without intersection, then only intersection of new & old, at last the old without intersection.
            env: for solver funcs

        ## Devs says
        ### Difference between `auto` & `solver`
            `jsonc_sdict` plan to have other program lang's version, so
            `auto` is cross-platform rule, but `solver` is specify on different dependency(eg: python is `DeepDiff`)
        """
        ddRestore = True
        ddPaths: set[tuple] = set()
        if isinstance(old_new, DeepDiffProtocol):
            if old_new.view != "tree":
                raise ValueError(f"{old_new.view=} should be 'tree' when init DeepDiff")
            if dictDict is not None:
                Log.warning(
                    "dictDict disabled, because dictDict() should run before DeepDiff()"
                )
            self.root = cast(DeepDiff, old_new)
        else:
            old, new = old_new
            if dictDict is not None:
                ddRestore = dictDict.pop("restore", True)
                old, new, ddPaths = self._dictDict(old, new, **dictDict)
            self.root = DeepDiff(old, new, **deepdiff_args)
        self.node = self.root
        self.env = self.Env(
            auto=auto,
            skdv=sameKey_diffValue,
            ddPaths=ddPaths,
            ddRestore=ddRestore,
            **env,
        )
        Log.debug(f"{self.root=}\t{self.env=}")
        self._iter = self._new_iter()
        self._iter_started = False

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> Self:
        ret = next(self._iter)
        if not self._iter_started:
            self._iter_started = True
        return ret

    def _new_iter(self) -> Generator[Self, Any, T1]:
        diffTypes = cast(Iterable[Type_DiffReport], self.root.keys())
        for dt in diffTypes:
            self.env.diffType = dt
            diffs: Iterable[DeepDiff] = self.root[dt]
            Log.debug(f"{dt=}\t{self.env.diffType=}")
            for d in diffs:
                self.node = d
                self._set_keypath(d)
                Log.debug(f"{d.keypath=}\t{type(d.t1)} {d.t1=}\t{type(d.t2)} {d.t2=}")
                yield self
        # TODO: restore dictDict to original list[dict...] by dictPath
        return self.merged

    def _set_keypath(self, node: DeepDiff | DiffLevel | None = None) -> list:
        if node is None:
            node = self.node
        node.keypath = tuple(node.path(output_format="list"))
        return node.keypath  # type: ignore


if __name__ == "__main__":
    result = merge(({0: 0}, {0: 0})).solve().merged
    print("☀", result)

    for _ in (self := merge(({0: 0}, {0: 1}), sameKey_diffValue="new")):
        self.solve()
    result = self.merged
    print("☀", result)
