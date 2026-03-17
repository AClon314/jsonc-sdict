"""
merge & preset
"""

from functools import cached_property
from types import MappingProxyType
from typing import (
    get_args,
    overload,
    Any,
    Self,
    Literal,
    Callable,
    TypeGuard,
    Union,
    FrozenSet,
    cast,
    TypedDict,
)
from collections.abc import (
    MutableMapping,
    MutableSequence,
    MutableSet,
    Iterable,
    Generator,
    Mapping,
)

from deepdiff import DeepDiff

from jsonc_sdict.share import NONE, iterable, getLogger
from jsonc_sdict.sdict import (
    set_item_attr,
    get_item_attr_raise,
    del_item_attr,
)

Log = getLogger(__name__)


type MergeFallback = Literal["old", "new", "del", "yield"]
type SetPart = Literal["old", "new", "old-^", "new-^", "^"]
set_parts = get_args(SetPart)
type TupleSetPart = (
    tuple[()]
    | tuple[SetPart]
    | tuple[SetPart, SetPart]
    | tuple[SetPart, SetPart, SetPart]
)
type IsType[T, *TS] = type[T] | tuple[*TS] | Callable[[Any], bool]
"""dict | (dict,) | lambda obj: isinstance(obj, dict)"""


@overload
def isType[T](obj, types: type[T]) -> TypeGuard[T]: ...


# https://github.com/python/mypy/issues/16720
@overload
def isType[*T](obj, types: tuple[*T]) -> TypeGuard[Union[*T]]: ...  # type: ignore


@overload
def isType(obj, types: Callable[[Any], bool]) -> bool: ...


def isType(obj, types: IsType) -> bool:
    """if callable, then need manually `obj=cast(type, obj)`"""
    return types(obj) if callable(types) else isinstance(obj, types)


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


class PatchDeepDiff[T](DeepDiff):
    t1: T
    t2: T
    up: Self
    """parent"""
    down: Self
    path: Callable

    @cached_property
    def keypath(self) -> list:
        return self.path(output_format="list")  # type: ignore


class merge[T]:
    """preset for `auto` arg
    🎃 Issue/Pull Request welcome! share your preset! 👻 \n
    创建Issue或PR来分析你的预设，帮助大家节省时间!
    """

    _Func = Callable[[type[Self], PatchDeepDiff, PatchDeepDiff], Any]
    """cls, root_diff, node_diff"""
    Func = Callable[[PatchDeepDiff, PatchDeepDiff], Any]
    """`func = cast(merge.Func, func)`"""
    type AutoDict = dict[IsType, TupleSetPart | Literal["del", "yield"] | _Func]
    """{dict: "del", (MyMap, sdict): (), lambda obj: isinstance(obj, Sequence) and not isinstance(obj, (str,bytes)): ("old")}"""
    type HookKey = DiffReportType | Literal["else"]
    type HookValue = tuple[_Func | Literal["yield"], ...] | MergeFallback
    type Hook = dict[HookKey, HookValue]

    get_item = staticmethod(get_item_attr_raise)
    set_item = staticmethod(set_item_attr)
    del_item = staticmethod(del_item_attr)

    auto_old_new: AutoDict = {iterable: ("old", "new-^")}
    auto_new_old: AutoDict = {iterable: ("new", "old-^")}

    @classmethod
    def hook_keepImmutable(cls, root: PatchDeepDiff, diff: PatchDeepDiff, **envs):
        """by default, keep old's immutable types wherever it appears."""
        t1 = diff.t1
        # t2 = diff.t2
        if isinstance(t1, tuple):
            t1 = tuple(t1)
        elif isinstance(t1, MappingProxyType):
            t1 = MappingProxyType(t1)
        elif isinstance(t1, FrozenSet):
            t1 = frozenset(t1)
        cls.set_item(root.t1, diff.keypath, t1)
        return t1

    @classmethod
    def hook_forceImmutable(cls, root: PatchDeepDiff, diff: PatchDeepDiff, **envs):
        """keep old's all immutable."""
        t1 = diff.t1
        if isinstance(t1, MutableSequence):
            t1 = tuple(t1)
        elif isinstance(t1, MutableMapping):
            t1 = MappingProxyType(t1)
        elif isinstance(t1, MutableSet):
            t1 = frozenset(t1)
        cls.set_item(root.t1, diff.keypath, t1)
        return t1

    @classmethod
    def hook_sameKey_diffValue(
        cls,
        root: PatchDeepDiff,
        diff: PatchDeepDiff,
        sameKey_diffValue: MergeFallback = "new",
        **envs,
    ) -> Generator[PatchDeepDiff, Any, None]:
        """
        **before applying `auto` rule**, you need to solve different scalar old&new value in same key.
        eg: old={"same": 1}, new={"same": 2} or new={"same": "1"} or new={"same": [...]}
        eg-both_container-but_type_mismatch: old={"same": [...]}, new={"same": {...}}
        But these would **NOT** apply `sameKey_diffValue` rule, they directly apply `auto` rule:
        eg-allList: old={"same": [...]}, new={"same": [...]}
        eg-allDict: old={"same": {...}}, new={"same": {...}}
        """
        t1 = diff.t1
        t2 = diff.t2
        if iterable(t1) and iterable(t2) or t1 == t2:
            return
        if sameKey_diffValue == "yield":
            yield from cls.Yield(root, diff)
        elif sameKey_diffValue == "del":
            cls.del_item(root.t1, diff.keypath)
        elif sameKey_diffValue == "old":
            cls.set_item(root.t1, diff.keypath, diff.t1)
        elif sameKey_diffValue == "new":
            cls.set_item(root.t1, diff.keypath, diff.t2)

    @classmethod
    def hook_auto(
        cls,
        root: PatchDeepDiff,
        diff: PatchDeepDiff,
        auto: AutoDict | None = None,
        **envs,
    ) -> Generator[PatchDeepDiff, Any, None]:
        """execute auto rule"""
        if not auto:
            yield from cls.Yield(root, diff)
            return
        old = diff.t1
        new = diff.t2
        for types, rule in auto.items():
            if not (isType(diff.t1, types) and isType(diff.t2, types)):
                # 未命中rule
                Log.debug(f"{types=}")
                continue
            # most common case at front
            if isinstance(rule, tuple):
                if not rule:
                    # ()
                    cls.set_item(root.t1, diff.keypath, diff.t1.__class__())
                elif rule == ("old"):
                    pass
                elif rule == ("new"):
                    cls.set_item(root.t1, diff.keypath, new)
                else:
                    # TODO
                    Log.debug(f"{rule=}\t{diff=}")
                    intersect = set(old) & set(new)
            elif callable(rule):
                rule = cast(merge.Func, rule)
                rule(root, diff)
                # cls.set_item(root.t1, diff.keypath, merged)
            elif rule == "del":
                cls.del_item(root.t1, diff.keypath)
            elif rule == "yield":
                yield from cls.Yield(root, diff)
            else:
                raise ValueError(f"invalid {{{types}:{rule}}} from {auto=}")

    hook_default: Hook = {
        "values_changed": (hook_sameKey_diffValue, hook_auto),
        "type_changes": "yield",
        "repetition_change": "yield",
        "else": (hook_auto,),
    }

    """
    ```python
    my_hooks: Hook = (*merge.hook_default, hook_keepImmutable)
    ```
    """

    deepdiff = dict(
        view="tree",
        ignore_type_in_groups=[
            (MutableMapping,),
            (MutableSequence,),
            (MutableSet,),
        ],
    )
    """see [DeepDiff](https://zepworks.com/deepdiff/current/ignore_types_or_values.html#ignore-type-in-groups), by default will ignore type_changes to focus on data changes."""

    @classmethod
    def Yield(
        cls, root: PatchDeepDiff, node: PatchDeepDiff
    ) -> Generator[PatchDeepDiff, Any, None]:
        NEW_V = yield node
        if NEW_V is not None:
            if NEW_V is NONE:
                NEW_V = None
            cls.set_item(root.t1, node.keypath, NEW_V)

    @classmethod
    def exec_hook(
        cls,
        hook: Hook,
        key: HookKey,
        root: PatchDeepDiff,
        node: PatchDeepDiff,
        env: Mapping[str, Any] = {},
    ) -> Generator[PatchDeepDiff, Any, None]:
        """execute hook rule"""
        for h, funcs in hook.items():
            if isinstance(funcs, tuple):
                for func in funcs:
                    # only when "global", ... includes "auto" and sub-hooks
                    if func == "yield":
                        yield from cls.Yield(root, node)
                    elif callable(func):
                        func = cast(merge.Func, func)
                        func(root, node, **env)
                    else:
                        raise ValueError(f"invalid {func} from {{{key}:{funcs}}}")
            elif funcs == "yield":
                yield from cls.Yield(root, node)
            elif funcs == "new":
                cls.set_item(root.t1, node.keypath, node.t2)
            elif funcs == "old":
                pass
            elif funcs == "del":
                cls.del_item(root.t1, node.keypath)

    def __new__(
        cls,
        old_new: tuple[Iterable, Iterable] | PatchDeepDiff[T] | DeepDiff,
        auto: AutoDict | None = auto_old_new,
        hook: Hook = hook_default,
        getItemFunc: Callable[[Any, Any], Any] = get_item,
        setItemFunc: Callable[[Any, Any, Any], Any] = set_item,
        delItemFunc: Callable[[Any, Any], Any] = del_item,
        sameKey_diffValue: MergeFallback = "new",
        **env,
    ) -> Generator[PatchDeepDiff[T], Any, Any]:
        """
        if new is dict or Map, will auto convert into DeepDiff internally.
        *inspired by [deepmerge](https://github.com/toumorokoshi/deepmerge) & [deepdiff](https://github.com/seperman/deepdiff) with [this issue](https://github.com/seperman/deepdiff/issues/552)*
        ```python
        for diff in (gen := merge((old, new))):
            NEW_V = diff.t1
            gen.send(NEW_V)
        ```

        Args:
            old_new: also accepct **`DeepDiff(t1, t2, **preset.deepdiff)`**
                will update the `old`, but you can use `old2 = deepcopy(old)` and pass like `old_new=(old2, new)`, see [Destructive Merge](https://deepmerge.readthedocs.io/en/latest/guide.html#merges-are-destructive)
            auto: static rule to auto resolve conflict. *(`Set` has no order)*
                - if not match any rule at last, will yield.
                    If call `send(None)` or not call `gen.send(NEW_V)` before `next()`, will preserve **old**'s key-value pair.
                - `()` means {"preserve key & value container, but no values": []}
                - "del" means {}, del key-value pair.
                - `("old", "new-^")` means, old k:v within **intersection as ^** are **in front of** new k:v with**out** intersection.
                - `("new",)` means only new, no old.
                - `("new-^", "^", "old-^")` means new without intersection, then only intersection of new & old, at last the old without intersection.
            hook: see `hooks_default`, I absctract the hook funcs for `DeepDiff`'s `report type`, use this when `auto` is not enough.
            sameKey_diffValue: see `hook_sameKey_diffValue()`
            **env: for hook funcs

        Returns:
            old

        ## Send
            NEW_V: if you don't want to use new_v, you send your wanted value here
        """
        diff: PatchDeepDiff
        if isinstance(old_new, DeepDiff):
            old = old_new.t1
            new = old_new.t2
            diff = old_new  # type: ignore
        else:
            old, new = old_new
            diff = DeepDiff(old, new, **merge.deepdiff)  # type: ignore
            if diff.view != "tree":
                raise ValueError(f"{diff.view=} should be 'tree' when init DeepDiff")

        cls.get_item = getItemFunc
        cls.set_item = setItemFunc
        cls.del_item = delItemFunc

        env = dict(auto=auto, **env)
        diff_keys = set(diff.keys())
        hook_keys = set(hook.keys())
        elseKeys = set(diff_keys) - set(hook_keys)

        for key in hook:
            if key not in diff_keys:
                continue
            elif key == "else":
                keys = elseKeys
            else:
                keys = [key]
            for k in keys:
                diffs: Iterable[PatchDeepDiff] = diff[k]
                for d in diffs:
                    d.keypath = d.path(output_format="list")
                    Log.debug(f"{d.keypath=}")
                    Log.debug(f"{d.t1=}")
                    Log.debug(f"{d.t2=}")

                    for why_yield in (
                        gen := cls.exec_hook(hook, key, root=diff, node=d, env=env)
                    ):
                        NEW_V = yield d
                        gen.send(NEW_V)
        return old
