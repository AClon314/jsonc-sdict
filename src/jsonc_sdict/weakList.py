"""
wrapper of Weak*Dictionary
"""

import sys
from weakref import WeakKeyDictionary, WeakValueDictionary
from collections.abc import Callable, Iterable, MutableSet, Sequence, Sized, Iterator
from typing import Any, Protocol
from useful_types import SupportsDunderGT, SupportsDunderLT

from jsonc_sdict.share import RAISE, check_hashWeak


class Comparable[V](Iterable[V], Sized, Protocol):
    def __iter__(self) -> Iterator[V]: ...
    def __len__(self) -> int: ...
    def __lt__(self, other: Iterable[V]) -> bool: ...
    def __le__(self, other: Iterable[V]) -> bool: ...
    def __gt__(self, other: Iterable[V]) -> bool: ...
    def __ge__(self, other: Iterable[V]) -> bool: ...


class WeakList[H](Sequence[H]):
    """
    If you hate strict type, init like `wl=Weaklist[Any](...)` or `wl=Weaklist[..., Any](...)`

    Inner:
        self.dict.keys(), new key > old last key, `1,2,7,11,[new_key>11]`
    """

    dict: WeakValueDictionary[int, H]
    """WeakList is a wapper of WeakValueDictionary"""

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
        """find/gen un-occupied key (O(1) optimization)"""
        k = self._next_key
        self._next_key += 1
        return k

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
                `WeakList([{},[]])` ❌ NO, dict/list has NO __hash__ \n
                `WeakList([1,2])` ❌ NO, basic type has NO __weakref__
            noRepeat: promise **no repeat items like ordered set**\n
                WeakList(..., noRepeat=True) != OrderedWeakSet() when:
                ```python
                v1, v2 = Ref(1), Ref(2)
                wl = WeakList([v1, v2], noRepeat=True)
                ws = OrderedWeakSet([v1, v2])
                print(wl, ws) # 1,2
                wl.append(v1)
                ws.append(v1)
                print(wl) # 2, 1    # respect user's latest/newest index order
                print(ws) # 1, 2    # deny repeated obj, and keep original order
                ```
        """
        self.dict = WeakValueDictionary()
        self.noRepeat = noRepeat
        self._next_key = 0
        self.dict_swap: WeakKeyDictionary[H, int] = WeakKeyDictionary()
        """internal use this as {value: key} cache to be faster when noRepeat==True"""

        self.extend(data)
        self.iterRefs = self.dict.itervaluerefs

    def __repr__(self) -> str:
        if not self:
            return f"{self.__class__.__name__}()"
        return f"{self.__class__.__name__}({list(self)})"

    def __hash__(self) -> int:
        return id(self)

    def __lt__(self, other: Comparable[H]):
        return self._cmp(other, lambda a, b: a < b)

    def __le__(self, other: Comparable[H]):
        return self._cmp(other, lambda a, b: a <= b)

    def __eq__(self, value: Comparable[H]) -> bool:
        if self is value:  # id(self) == id(value)
            return True
        return self._cmp(value, lambda a, b: a == b)

    def __ne__(self, value: Comparable[H]) -> bool:
        if self is value:
            return False
        return self._cmp(value, lambda a, b: a != b)

    def __gt__(self, other: Comparable[H]):
        return self._cmp(other, lambda a, b: a > b)

    def __ge__(self, other: Comparable[H]):
        return self._cmp(other, lambda a, b: a >= b)

    def __iter__(self):
        return iter(self.dict.values())

    # __iter__ will do Error check/raise
    def __next__(self): ...

    def __len__(self) -> int:
        return len(self.dict)

    def __getitem__(self, index: int | slice[int | None]) -> H | list[H]:
        if isinstance(index, slice):
            return list(self)[index]
        # values() is O(1) in current dict, but indexing into it is O(n)
        return list(self.dict.values())[index]

    def __setitem__(self, index: int, value: H) -> None:
        K = self._getkey(index)

        if self.noRepeat:
            if value in self.dict_swap:
                existing_key = self.dict_swap[value]
                if existing_key == K:
                    return
                del self.dict[existing_key]
        old_val = self.dict[K]
        self.dict[K] = value
        self.dict_swap[value] = K

        if old_val is not None and old_val != value:
            if not self.noRepeat:
                exists = False
                for k, v in self.dict.items():
                    if v == old_val:
                        self.dict_swap[old_val] = k
                        exists = True
                        break
                if not exists:
                    self.dict_swap.pop(old_val, None)
            else:
                self.dict_swap.pop(old_val, None)

    def __delitem__(self, index: int):
        K = self._getkey(index)
        val = self.dict[K]
        del self.dict[K]
        if val is not None:
            if self.noRepeat:
                self.dict_swap.pop(val, None)
            else:
                # Find another occurrence for dict_swap
                exists = False
                for k, v in self.dict.items():
                    if v == val:
                        self.dict_swap[val] = k
                        exists = True
                        break
                if not exists:
                    self.dict_swap.pop(val, None)

    def __add__(self, other: Iterable):
        wl = self.copy()
        wl.extend(other)
        return wl

    def __iadd__(self, other: Iterable):
        self.extend(other)
        return self

    def __mul__(self, other: int):
        if other < 1:
            return WeakList(noRepeat=self.noRepeat)
        wl = self.copy()
        for _ in range(other - 1):
            wl.extend(self)
        return wl

    def __rmul__(self, other: int):
        return self.__mul__(other)

    def __imul__(self, other: int):
        if other < 1:
            self.clear()
            return self
        if other <= 1:
            return self

        original_data = list(self)
        for _ in range(other - 1):
            self.extend(original_data)
        return self

    def __contains__(self, value: object) -> bool:
        if self.noRepeat:
            return value in self.dict_swap
        return value in self.dict.values()

    def __reversed__(self):
        # Dict is ordered, so we can reverse its items
        for k, v in reversed(list(self.dict.items())):
            yield k, v

    def clear(self) -> None:
        self.dict.clear()
        self.dict_swap.clear()
        self._next_key = 0

    def copy(self):
        return self.__class__(self, noRepeat=self.noRepeat)

    def append(self, obj: H) -> None:
        if self.noRepeat and obj in self.dict_swap:
            existing_key = self.dict_swap[obj]
            del self.dict[existing_key]

        key = self._newkey()
        self.dict[key] = obj
        self.dict_swap[obj] = key

    def insert(self, index: int, obj: H) -> None:
        current_len = len(self)
        if index < 0:
            index += current_len
        index = max(0, min(index, current_len))

        current_values = list(self.dict.values())
        if self.noRepeat:
            try:
                old_idx = -1
                for i, v in enumerate(current_values):
                    if v == obj:
                        old_idx = i
                        break

                if old_idx != -1:
                    if old_idx == index:
                        return
                    current_values.pop(old_idx)
                    # No need to adjust index; insert(index, obj) should put it at 'index'
            except ValueError:
                pass

        current_values.insert(index, obj)

        self.clear()
        self.extend(current_values)

    def extend(self, iterable: Iterable) -> None:
        for item in iterable:
            self.append(item)

    def pop[D](self, index: int = -1, default: D = RAISE) -> H | D:
        try:
            if index == -1:
                K, v = self.dict.popitem()
            else:
                K = self._getkey(index)
                v = self.dict[K]
                del self.dict[K]

            if self.noRepeat:
                self.dict_swap.pop(v, None)
            else:
                # Find another occurrence for dict_swap
                exists = False
                for k, val in self.dict.items():
                    if val == v:
                        self.dict_swap[v] = k
                        exists = True
                        break
                if not exists:
                    self.dict_swap.pop(v, None)
            return v
        except Exception as e:
            if default is RAISE:
                raise IndexError(index) from e
            return default

    def remove(self, value: H) -> None:
        if self.noRepeat:
            K = self.dict_swap.get(value)
            if K is not None:
                del self.dict[K]
                del self.dict_swap[value]
                return
            raise ValueError(f"{value} not in list")

        for k, v in self.dict.items():
            if v == value:
                del self.dict[k]
                # Update dict_swap to another occurrence if available
                exists = False
                for k2, v2 in self.dict.items():
                    if v2 == value:
                        self.dict_swap[value] = k2
                        exists = True
                        break
                if not exists:
                    self.dict_swap.pop(value, None)
                return
        raise ValueError(f"{value} not in list")

    def index(self, value: H, start: int = 0, stop: int = sys.maxsize) -> int:
        return self.tuple.index(value, start, stop)

    def count(self, value: H) -> int:
        if self.noRepeat:
            return 1 if value in self.dict_swap else 0
        return list(self).count(value)

    def reverse(self) -> None:
        items = list(self)
        items.reverse()
        self.clear()
        self.extend(items)

    def sort(
        self,
        *,
        key: Callable[[H], SupportsDunderLT[H] | SupportsDunderGT[H]],
        reverse: bool = False,
    ) -> None:
        sorted_items = sorted(self, key=key, reverse=reverse)
        self.clear()
        self.extend(sorted_items)


class OrderedWeakSet[H](MutableSet[H]):
    """
    Ordered set that holds weak references (WeakOrderedSet).
    Elements must be hashable and support weak references.
    """

    @property
    def refs(self):
        return self.dict.keyrefs()

    def __init__(self, data: Iterable[H] = ()) -> None:
        self.dict: WeakKeyDictionary[H, None] = WeakKeyDictionary()
        for item in data:
            self.add(item)

    def __contains__(self, x: object) -> bool:
        return x in self.dict

    def __len__(self) -> int:
        return len(self.dict)

    def __iter__(self):
        return iter(self.dict.keys())

    def add(self, value: H) -> None:
        self.dict[value] = None

    def discard(self, value: H) -> None:
        if value in self.dict:
            del self.dict[value]

    def __repr__(self) -> str:
        if not self:
            return f"{self.__class__.__name__}()"
        return f"{self.__class__.__name__}({list(self)})"

    def __hash__(self) -> int:
        return id(self)

    def copy(self):
        return self.__class__(self)

    def __getitem__(self, index: int | slice[int | None]) -> H | list[H]:
        if isinstance(index, slice):
            return list(self.dict.keys())[index]
        return list(self.dict.keys())[index]


class Ref[V]:
    """strong reference"""

    def __init__(self, v: V | None = None) -> None:
        self.v = v

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return f"Ref({self.v})"

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, Ref):
            return self.v < other.v
        return self.v < other

    def __le__(self, other: Any) -> bool:
        if isinstance(other, Ref):
            return self.v <= other.v
        return self.v <= other

    def __eq__(self, value: object) -> bool:
        if isinstance(value, Ref):
            return self.v == value.v
        return self.v == value

    def __ne__(self, value: object) -> bool:
        return not self.__eq__(value)

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, Ref):
            return self.v > other.v
        return self.v > other

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, Ref):
            return self.v >= other.v
        return self.v >= other
