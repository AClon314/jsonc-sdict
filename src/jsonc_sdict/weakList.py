import sys
from warnings import deprecated
from weakref import WeakKeyDictionary, WeakValueDictionary
from collections.abc import Callable, Iterable, Sequence, Sized
from typing import AbstractSet, Any, Protocol, cast
from useful_types import SupportsDunderGT, SupportsDunderLT

from jsonc_sdict.share import RAISE, check_hashWeak, get_caller


class WeakList[H, O = H](Sequence[H]):
    """
    If you hate strict type, init like `wl=Weaklist[Any](...)` or `wl=Weaklist[..., Any](...)`

    Inner:
        self.dict.keys(), new key > old last key, `1,2,7,11,[new_key>11]`
    """

    dict: WeakValueDictionary[int, H]
    """WeakList is a wapper of WeakValueDictionary"""

    def __getattribute__(self, name: str) -> Any:
        """turn off when release"""
        if name not in ("dict"):
            print(dict(self.dict), "\t", get_caller())
        return super().__getattribute__(name)

    @property
    def refs(self):
        """like `ref`, call to get & hold value: `value = wl.refs[0]()`,\n
        also this create strong references

        The references are NOT guaranteed to be 'live' at the time they are used,\n
        so the result of calling the references **needs to be checked before** being used.\n
        """
        return self.dict.valuerefs()

    @property
    def tuple(self):
        """do NOT hold this, otherwise it becomes strong references\n
        if you really want to hold, try `refs` or `iterRefs()`
        ```python
        obj = HashableObj()
        wl = WeakList([obj])
        hold_values = wl.tuple
        del obj
        len(wl) # 1
        del hold_values
        len(wl) # 0
        ```
        """
        return tuple(self.dict.values())

    def _getkey(self, index: int) -> int:
        """list index to dict key"""
        K = None
        for i, k in enumerate(self.dict.keys()):
            if i == index:
                K = k
                break
        if K is None:
            raise IndexError(index)
        return K

    def _newkey(self) -> int:
        """find/gen un-occupied key"""
        keys = tuple(self.dict.keys())
        idx = keys[-1] + 1 if keys else 0
        while idx in keys:
            idx += 1
        return idx

    def _cmp(
        self,
        other: Comparable,
        cmp: Callable[[Any, Any], bool],
    ):
        for i, j in zip(self, other):
            if i == j:
                continue
            return cmp(i, j)
        return cmp(len(self), len(other))

    def __init__(self, data: Iterable[H] = (), noRepeat=False):
        """
        Args:
            data: support both `__hash__` and `__weakref__`, otherwise raise TypeError\n
                `OrderedWeakSet([{},[]])` ❌ NO, dict/list has NO __hash__ \n
                `OrderedWeakSet([1,2])` ❌ NO, basic type has NO __weakref__
            noRepeat: promise **no repeat items like ordered set**
        """
        if noRepeat:
            data = {r: None for r in (data)}
        _dict = {i: r for i, r in enumerate(data)}
        self.dict = WeakValueDictionary(_dict)
        self.noRepeat = noRepeat
        self.iterRefs = self.dict.itervaluerefs

    def __repr__(self) -> str:
        return str(self.tuple)

    def __hash__(self) -> int:
        return id(self)

    def __lt__(self, other: Comparable[O]):
        return self._cmp(other, lambda a, b: a < b)

    def __le__(self, other: Comparable[O]):
        return self._cmp(other, lambda a, b: a <= b)

    def __eq__(self, value: Comparable[O]) -> bool:
        if self is value:  # id(self) == id(value)
            return True
        return self._cmp(value, lambda a, b: a == b)

    def __ne__(self, value: Comparable[O]) -> bool:
        if self is value:
            return False
        return self._cmp(value, lambda a, b: a != b)

    def __gt__(self, other: Comparable[O]):
        return self._cmp(other, lambda a, b: a > b)

    def __ge__(self, other: Comparable[O]):
        return self._cmp(other, lambda a, b: a >= b)

    def __iter__(self):
        for i in self.dict.values():
            yield i

    # __iter__ will do Error check/raise
    def __next__(self): ...

    def __len__(self) -> int:
        return len(self.tuple)

    def __getitem__(self, key: int | slice[int, int, int]) -> H:
        return self.tuple[key]

    def __setitem__(self, key: int, value: H) -> None:
        K = None
        K_DEL = None
        for i, (k, v) in enumerate(self.dict.items()):
            if i == key:
                K = k
            if K_DEL is None and v == value:
                K_DEL = k
            if K and (not self.noRepeat or K_DEL):
                break
        if K is None:
            raise IndexError(key)
        if K == K_DEL:
            return
        self.dict[K] = value
        if K_DEL is not None:
            del self.dict[K_DEL]

    def __delitem__(self, key: int):
        del self.dict[self._getkey(key)]

    def __add__(self, other: Iterable[O]):
        wl = self.copy()
        key = self._newkey()
        new_dict = {i + key: v for i, v in enumerate(other)}
        wl.dict.update(new_dict)
        return wl

    def __iadd__(self, other: Iterable[O]):
        key = self._newkey()
        new_dict = {i + key: v for i, v in enumerate(other)}
        self.dict.update(new_dict)
        return self

    def __mul__(self, other: int):
        wl = self.copy()
        if other < 1:
            return WeakList(noRepeat=self.noRepeat)
        elif other == 1:
            return wl
        
        length = len(self)
        key = self._newkey()
        new_dict = {
            (o * length) + i + key: v 
            for o in range(other - 1) 
            for i, v in enumerate(self)
        }
        wl.dict.update(new_dict)
        return wl

    def __rmul__(self, other: int):
        return self.__mul__(other)

    def __imul__(self, other: int):
        if other < 1:
            self.dict.clear()
            return self
        if other <= 1:
            return self
            
        length = len(self)
        key = self._newkey()
        new_dict = {
            (o * length) + i + key: v 
            for o in range(other - 1) 
            for i, v in enumerate(self)
        }
        self.dict.update(new_dict)
        return self

    def __contains__(self, item: H) -> bool:
        return item in self.dict.values()

    def __reversed__(self):
        for k, v in reversed(tuple(self.dict.items())):
            yield k, v

    def clear(self) -> None:
        self.dict.clear()

    def copy(self):
        return WeakList(self.dict.values(), noRepeat=self.noRepeat)

    def append(self, object: H) -> None:
        key = self._newkey()
        self.dict[key] = object

    def insert(self, index: int, obj: H) -> None:
        """
        Insert an object at the given index.

        Args:
            index: Position to insert the object (supports negative indices,
                   0 ≤ normalized index ≤ len(self) is allowed).
            obj: The object to insert (MUST support both __hash__ and __weakref__).

        Raises:
            TypeError: If the object lacks __hash__ or __weakref__ (required for WeakValueDictionary).
            IndexError: If the index is out of bounds (after normalizing negative indices).
        """
        # 1. 处理索引标准化（兼容负数）
        current_len = len(self)
        if index < 0:
            index += current_len
        index = max(0, min(index, current_len))

        # 2. 核心插入逻辑：先获取当前有序值
        current_values = list(self.dict.values())

        # 3. 处理noRepeat：若开启去重，先删除已存在的重复项
        if self.noRepeat:
            try:
                old_idx = current_values.index(obj)
                current_values.pop(old_idx)
                # 如果删除的元素在插入位置之前，后续插入逻辑的索引需要前移
                if old_idx < index:
                    index -= 1
            except ValueError:
                pass

        # 4. 在指定位置插入
        current_values.insert(index, obj)
        
        # 5. 重构dict以保证有序性和key连续性
        new_dict = {i: val for i, val in enumerate(current_values)}
        self.dict.clear()
        self.dict.update(new_dict)

    def extend(self, iterable: Iterable[O]) -> None:
        key = self._newkey()
        new_dict = {i + key: v for i, v in enumerate(iterable)}
        self.dict.update(new_dict)

    def pop[D](self, index: int = -1, default: D = RAISE) -> H | D:
        """
        Remove and return item at index.

        Raises IndexError if list is empty or index is out of range.
        Args:
            index: default last.
        """
        try:
            if index == -1:
                v = self.dict.popitem()[1]
            else:
                k = self._getkey(index)
                v = self.dict[k]
                del self.dict[k]
        except Exception as e:
            if default is RAISE:
                raise IndexError(index, e)
            v = default
        return v

    def remove(self, value: H) -> None:
        for k, v in self.dict.items():
            if v == value:
                del self.dict[k]
                break

    def index(self, value: H, start: int = 0, stop: int = sys.maxsize) -> int:
        return self.tuple.index(value, start, stop)

    def count(self, value: H) -> int:
        return self.tuple.count(value)

    def reverse(self) -> None:
        self.dict = WeakValueDictionary(self.__reversed__())

    def sort(
        self,
        *,
        key: Callable[[H], SupportsDunderLT[H] | SupportsDunderGT[H]],
        reverse: bool = False,
    ) -> None:
        sorted_items = sorted(self, key=key, reverse=reverse)
        new_dict = {i: item for i, item in enumerate(sorted_items)}
        self.dict = WeakValueDictionary(new_dict)


class OrderedWeakSet[H, O = H](AbstractSet[H]):
    """WeakOrderedSet"""

    # __repr__, __hash__, __lt__, __le__, __eq__, __ne__, __gt__, __ge__, __iter__, __init__, __sub__, __rsub__, __and__, __rand__, __xor__, __rxor__, __or__, __ror__, __isub__, __iand__, __ixor__, __ior__, __len__, __contains__, add, clear, copy, discard, difference, difference_update, intersection, intersection_update, isdisjoint, issubset, issuperset, pop, __reduce__, remove, __sizeof__, symmetric_difference, symmetric_difference_update, union, update, __class_getitem__, __doc__

    @property
    def tuple(self):
        return tuple(self.dict.keys())

    def __init__(self, data: Iterable[H] = ()) -> None:
        _dict = {r: None for r in data}
        self.dict = WeakKeyDictionary(_dict)

    def __repr__(self) -> str:
        return f"{{{self.tuple}}}"

    def __hash__(self) -> int:
        return id(self)


class Comparable[H, O = Any](Iterable[H], Sized, Protocol):
    ...
    # def __iter__(self) -> H: ...
    # def __len__(self) -> int: ...
    # def __lt__(self, other: Iterable[O]) -> bool: ...
    # def __le__(self, other: Iterable[O]) -> bool: ...
    # def __gt__(self, other: Iterable[O]) -> bool: ...
    # def __ge__(self, other: Iterable[O]) -> bool: ...


class Value[V = None]:
    def __init__(self, v: V = None) -> None:
        self.v = v

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return f"{self.v}"

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, Value):
            return self.v < other.v
        return self.v < other

    def __le__(self, other: Any) -> bool:
        if isinstance(other, Value):
            return self.v <= other.v
        return self.v <= other

    def __eq__(self, value: object) -> bool:
        if isinstance(value, Value):
            return self.v == value.v
        return self.v == value

    def __ne__(self, value: object) -> bool:
        return not self.__eq__(value)

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, Value):
            return self.v > other.v
        return self.v > other

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, Value):
            return self.v >= other.v
        return self.v >= other
