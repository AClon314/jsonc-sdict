"""
merge & preset
"""

from functools import cached_property
from types import MappingProxyType
from typing import (
    cast,
    get_args,
    overload,
    runtime_checkable,
    Any,
    Self,
    Union,
    Unpack,
    TypeIs,
    Literal,
    Callable,
    Protocol,
    FrozenSet,
)
from collections.abc import (
    Set,
    Mapping,
    Iterable,
    Generator,
    MutableMapping,
    MutableSequence,
    MutableSet,
)

from deepdiff import DeepDiff as _DeepDiff
from deepdiff.diff import DeepDiffProtocol as _DeepDiffProtocol

from jsonc_sdict.share import (
    NONE,
    RAISE,
    UNSET,
    iterable,
    getLogger,
    return_of,
    return_from,
)
from jsonc_sdict.sdict import (
    dfs,
    dictDict,
    get_item_attr,
    set_item_attr,
    del_item_attr,
    KwargsDictDict,
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

type MergeEnd = Literal["old", "new", "del", "yield"]
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


type DiffReportType = Literal[
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
    def keypath(self) -> list:
        return self.path(output_format="list")  # type: ignore


@runtime_checkable
class DeepDiffProtocol(_DeepDiffProtocol, Protocol): ...


class merge[T]:
    """preset for `auto` arg
    🎃 Issue/Pull Request welcome! share your preset! 👻 \n
    创建Issue或PR来分享你的预设，帮助大家节省时间!
    """

    _FuncReturn = bool | None
    _FuncOrGen = Generator[DeepDiff, Any, _FuncReturn] | _FuncReturn
    _HookFunc = Callable[[type[Self], DeepDiff, DeepDiff], _FuncOrGen]
    """cls, root_diff, node_diff -> del_conflict if True else continue"""
    HookFunc = Callable[[DeepDiff, DeepDiff], _FuncOrGen]
    """`func = cast(merge.Func, func)`"""
    AutoDict = dict[IsType, MergeOrder | MergeEnd | _HookFunc]
    """`{dict: "del", (MyMap, sdict): "", lambda obj:isinstance(obj,Sequence) and not isinstance(obj,(str,bytes)): "old"}`"""
    type HookKey = DiffReportType | Literal["else"]
    type HookValue = tuple[_HookFunc, ...] | MergeEnd
    type Hook = dict[HookKey, HookValue]

    @classmethod
    def get_item[D](
        cls,
        root: Any,
        node: DeepDiff,
        default: D | RAISE = RAISE,
        noRaise=(
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
        ),
    ) -> Any | D:
        """
        Args:
            root: `root.t1`/`root.t2`. if `root` then fallback to `root.t1`(old)
        """
        if isinstance(root, DeepDiffProtocol):
            root = root.t1
        return get_item_attr(root, node.keypath, default=default, noRaise=noRaise)

    @classmethod
    def set_item(cls, root: DeepDiff, node: DeepDiff, value=UNSET):
        """
        Args:
            value: by default use `t2`(new)
        """
        v = cls.get_item(root.t2, node) if value is UNSET else value
        set_item_attr(root.t1, node.keypath, v)
        # read the original __class__, we only edit root, not node
        # node.t1 = v

    @classmethod
    def del_item(cls, root: DeepDiff, node: DeepDiff):
        if cls.get_item(root.t1, node):
            del_item_attr(root.t1, node.keypath)
        else:
            Log.debug("⚠ Del but not existed: %s", node.keypath)

    auto_old_new: AutoDict = {Mapping: "old,new-^", iterable: "old,new-^"}
    auto_new_old: AutoDict = {Mapping: "old,new-^", iterable: "new,old-^"}

    @classmethod
    def hook_keepInitClass(cls, root: DeepDiff, node: DeepDiff, **env) -> None:
        """`node.t1.__class__(cls.get_item(root, node))`"""
        Cls = node.t1.__class__
        now = cls.get_item(root, node)
        cls.set_item(root, node, Cls(now))

    @classmethod
    def hook_keepImmutable(cls, root: DeepDiff, node: DeepDiff, **env) -> None:
        """by default, keep old's immutable types wherever it appears."""
        init = node.t1
        now = cls.get_item(root, node)
        if isinstance(init, tuple):
            v = tuple(now)
        elif isinstance(init, MappingProxyType):
            v = MappingProxyType(now)
        elif isinstance(init, FrozenSet):
            v = frozenset(now)
        cls.set_item(root, node, v)

    @classmethod
    def hook_forceImmutable(cls, root: DeepDiff, node: DeepDiff, **env) -> None:
        """keep old's all immutable."""
        now = cls.get_item(root, node)
        if isinstance(now, MutableSequence):
            v = tuple(now)
        elif isinstance(now, MutableMapping):
            v = MappingProxyType(now)
        elif isinstance(now, MutableSet):
            v = frozenset(now)
        cls.set_item(root, node, v)

    @classmethod
    def hook_sameKey_diffValue(
        cls,
        root: DeepDiff,
        node: DeepDiff,
        sameKey_diffValue: MergeEnd = "new",
        diffType: DiffReportType | RAISE = RAISE,
        **env,
    ) -> Generator[DeepDiff, Any, bool]:
        """
        Resolve **unmergeable** `dict` conflicts before applying `auto` rules. \n
        eg: old={"same": 1}, new={"same": 2} or new={"same": "1"} or new={"same": [...]}
        eg-both_container-but_type_mismatch: old={"same": [...]}, new={"same": {...}}
        But these would **NOT** apply `sameKey_diffValue` rule, they directly apply `auto` rule:
        eg-allList: old={"same": [...]}, new={"same": [...]}
        eg-allDict: old={"same": {...}}, new={"same": {...}}
        """
        if diffType is RAISE:
            raise ValueError("need `diffType` keyword arg")
        t1 = node.t1
        # t2 = node.t2
        if (
            diffType == "values_changed"
            and isinstance(t1, Mapping)
            and isinstance(t1, Mapping)
        ):
            # deepdiff don't handle dict
            # so give up and give control to next hook(usually `hook_auto`)
            return
        if sameKey_diffValue == "yield":
            yield from cls.yield_set(root, node)
        elif sameKey_diffValue == "del":
            cls.del_item(root, node)
        elif sameKey_diffValue == "old":
            pass
        elif sameKey_diffValue == "new":
            cls.set_item(root, node)

    @classmethod
    def _hook_intersect(
        cls,
        root: DeepDiff,
        node: DeepDiff,
        order: MergeOrder | RAISE = RAISE,
        diffType: DiffReportType | RAISE = RAISE,
        **env,
    ):
        """deepdiff report "values_changed" while dictA has no intersection with dictB"""
        old = cls.get_item(root.t1, node)
        new = cls.get_item(root.t2, node)
        all_iterable = iterable(old) and iterable(new)
        xor_map = isinstance(old, Mapping) ^ isinstance(new, Mapping)
        if not all_iterable or xor_map:
            raise ValueError(
                "old&new are not same type. Try to use `hook_sameKey_diffValue` before, or override/try...catch"
            )
        init = node.t1
        init_ret = order != "old,new-^"
        if isinstance(init, (Mapping, Set)):
            ret: dict | set = {} if init_ret else old

            def update(s):
                ret.update(s)

        else:
            ret: list = [] if init_ret else old

            def update(s):
                ret.extend(s)

        orders = cast(list[MergeOrderBase], order.split(","))
        if "^" in order:
            # TODO: dict ?
            o = set(old)
            n = set(new)
            intersect = o.intersection(n)
        for od in orders:
            if od == "^":
                item = intersect
            elif od == "old-^":
                item = o - intersect
            elif od == "new-^":
                item = n - intersect
            elif od == "old":
                item = old
            elif od == "new":
                item = new
            else:
                raise ValueError(f"invalid syntax={od} from {order=}")
            Log.debug(f"item=%s from od=%s", item, od)
            if init_ret:
                update(item)
        Log.debug("old=%s\tnew=%s\tret=%s", old, new, ret)
        cls.set_item(root, node, ret)

    @classmethod
    def hook_auto(
        cls,
        root: DeepDiff,
        node: DeepDiff,
        auto: AutoDict | None = None,
        **env,
    ) -> Generator[DeepDiff, Any, bool]:
        """auto merge"""
        hit = False
        if auto:
            for types, order in auto.items():
                if isType(node.t1, types) and isType(node.t2, types):
                    # 命中rule
                    hit = True
                    Log.debug(f"{types=}")
                    break
        if not (auto and hit):
            yield from cls.yield_set(root, node)
            return
        if callable(order):
            order = cast(merge.HookFunc, order)
            yield from return_from(order(root, node))
            # need invoke cls.set_item in rule()
            # no tuple[funcs...], so no del conflict
        elif order == "yield":
            yield from cls.yield_set(root, node)
        elif order == "del":
            cls.del_item(root.t1, node)
        elif order == "":
            # empty container
            cls.set_item(root, node, node.t1.__class__())
        elif order == "old":
            pass
        elif order == "new":
            cls.set_item(root, node)
        elif "^" in order:
            cls._hook_intersect(root, node, order, **env)
        else:
            raise ValueError(f"invalid {{{types}:{order}}} from {auto=}")

    hooks_allMutable: Hook = {
        "values_changed": (hook_sameKey_diffValue, hook_auto),
        "type_changes": (hook_sameKey_diffValue,),
        "repetition_change": "yield",
        "else": (hook_auto,),
    }
    hooks_keepImmutable: Hook = {
        "values_changed": (hook_sameKey_diffValue, hook_auto, hook_keepImmutable),
        "type_changes": (hook_sameKey_diffValue, hook_keepImmutable),
        "repetition_change": "yield",
        "else": (hook_auto, hook_keepImmutable),
    }

    deepdiff_args = dict(
        view="tree",
        ignore_type_in_groups=[
            (MutableMapping,),
            (MutableSequence,),
            (MutableSet,),
        ],
    )
    """see [DeepDiff](https://zepworks.com/deepdiff/current/ignore_types_or_values.html#ignore-type-in-groups), by default will ignore type_changes to focus on data changes."""

    @classmethod
    def yield_set(
        cls, root: DeepDiff, node: DeepDiff
    ) -> Generator[DeepDiff, Any, None]:
        """`yield from cls.yield_set(root, node)` will give control to outside that `gen.send(NEW_V)`"""
        NEW_V = yield node
        if NEW_V is not None:
            if NEW_V is NONE:
                NEW_V = None
            cls.set_item(root, node, NEW_V)

    @classmethod
    def exec_hook(
        cls,
        key: DiffReportType,
        value: HookValue,
        root: DeepDiff,
        node: DeepDiff,
        env: Mapping[str, Any] = {},
    ) -> Generator[DeepDiff, Any, None]:
        """execute hook rule"""
        if iterable(value):
            for func in value:
                if func == "yield":
                    yield from cls.yield_set(root, node)
                elif isinstance(func, (Callable, classmethod, staticmethod)):
                    env = {"diffType": key, **env}
                    if isinstance(func, classmethod):
                        func = func.__get__(None, cls)
                    func = cast(merge.HookFunc, func)
                    gen = func(root, node, **env)
                    ret: bool | None = yield from return_from(gen)
                    # NOTE: skip else funcs for current diff-node
                    if ret is True:
                        break
                else:
                    raise ValueError(f"invalid {func} from {{{key}:{value}}}")
        elif value == "yield":
            yield from cls.yield_set(root, node)
        elif value == "new":
            cls.set_item(root, node)
        elif value == "old":
            pass
        elif value == "del":
            cls.del_item(root, node)

    @staticmethod
    def dictDict(
        old, new, **kw: Unpack[KwargsDictDict]
    ) -> tuple[Any, Any, list[tuple]]:
        old, path_old = return_of(dictDict(dfs(old), **kw))
        new, path_new = return_of(dictDict(dfs(new), **kw))
        path = [*path_old, *path_new]
        return old, new, path

    def __new__(
        cls,
        old_new: tuple[Iterable, Iterable] | DeepDiff[T] | DeepDiff,
        dictDict: KwargsDictDict | None = {},
        sameKey_diffValue: MergeEnd = "new",
        auto: AutoDict | None = auto_old_new,
        hook: Hook = hooks_allMutable,
        getItemFunc: Callable[[type[Self], Any, Any], Any] = get_item,
        setItemFunc: Callable[[type[Self], Any, Any, Any], Any] = set_item,
        delItemFunc: Callable[[type[Self], Any, Any], Any] = del_item,
        env={},
    ) -> Generator[DeepDiff[T], Any, Any]:
        """
        if new is dict or Map, will auto convert into DeepDiff internally.
        *inspired by [deepmerge](https://github.com/toumorokoshi/deepmerge) & [deepdiff](https://github.com/seperman/deepdiff) with [this issue](https://github.com/seperman/deepdiff/issues/552)*
        ```python
        for diff in (gen := merge((old, new))):
            NEW_V = diff.t1
            gen.send(NEW_V)
        ```

        Args:
            old_new: also accepct **`DeepDiff(t1, t2, **preset.deepdiff)`** \n
                will update the `old`, but you can use `old2 = deepcopy(old)` and pass like `old_new=(old2, new)`, see [Destructive Merge](https://deepmerge.readthedocs.io/en/latest/guide.html#merges-are-destructive)
            idKey: set to `None` to disable `dictDict()`
            sameKey_diffValue: see `hook_sameKey_diffValue()`
            auto: auto resolve **mergeable** conflict, see `auto_default`
                - if not match any rule at last, will yield.
                    If call `send(None)` or not call `gen.send(NEW_V)` before `next()`, will preserve **old**'s key-value pair.
                - `""` means {"preserve key & value container, but no values": []}
                - "del" means {}, del key-value pair.
                - `"old,new-^"` means, old k:v within **intersection as ^** are **in front of** new k:v with**out** intersection.
                - `"new"` means only new, no old.
                - `"new-^,^,old-^"` means new without intersection, then only intersection of new & old, at last the old without intersection.
            hook: see `hooks_allMutable`, I absctract the hook funcs for `DeepDiff`'s `report type`, use this when `auto` is not enough.
            env: for hook funcs

        Returns:
            old

        ## Send
            NEW_V: if you don't want to use new_v, you send your wanted value here

        ## Dev
        ### Difference between `auto` & `hook`
            `jsonc_sdict` would have other program lang's version, so
            `auto` is cross-platform rule, but `hook` is specify on different dependency(pure-python is `DeepDiff`, TODO: substitute to c-lib for better performance)
        """
        if isinstance(old_new, DeepDiffProtocol):
            if old_new.view != "tree":
                raise ValueError(f"{old_new.view=} should be 'tree' when init DeepDiff")
            old = old_new.t1
            new = old_new.t2
            if dictDict is not None:
                old, new, dictPath = cls.dictDict(old, new, **dictDict)
            diff = cast(DeepDiff, old_new)
        else:
            old, new = old_new
            if dictDict is not None:
                old, new, dictPath = cls.dictDict(old, new, **dictDict)
            diff = DeepDiff(old, new, **cls.deepdiff_args)  # type: ignore

        cls.get_item = getItemFunc  # type:ignore
        cls.set_item = setItemFunc  # type:ignore
        cls.del_item = delItemFunc  # type:ignore

        env = dict(auto=auto, sameKey_diffValue=sameKey_diffValue, **env)
        diff_keys = set(diff.keys())
        hook_keys = set(hook.keys())
        elseKeys = set(diff_keys) - set(hook_keys)

        for hkey in hook:
            if hkey not in diff_keys:
                continue
            elif hkey == "else":
                diffTypes = elseKeys
            else:
                diffTypes = [hkey]
            diffTypes = cast(Iterable[DiffReportType], diffTypes)
            for dt in diffTypes:
                diffs: Iterable[DeepDiff] = diff[dt]
                for d in diffs:
                    d.keypath = d.path(output_format="list")
                    Log.debug(f"{d.keypath=}")
                    Log.debug(f"{d.t1=}")
                    Log.debug(f"{d.t2=}")

                    yield from cls.exec_hook(dt, hook[dt], root=diff, node=d, env=env)

        Log.debug(f"{diff.t1=}")
        # TODO: restore dictDict to original list[dict...] by dictPath
        return diff.t1
