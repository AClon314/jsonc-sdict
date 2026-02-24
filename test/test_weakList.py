import gc
import pytest

from jsonc_sdict.weakList import Ref, WeakList as weaklist, OrderedWeakSet
from share import get_caller


class WeakList(weaklist):
    def __getattribute__(self, name: str):
        if name not in ("dict", "_reverse_dict", "_next_key", "noRepeat"):
            try:
                # Use super().__getattribute__ to avoid recursion
                d = super().__getattribute__("dict")
                print(dict(d), "\t", get_caller())
            except AttributeError:
                pass
        return super().__getattribute__(name)


class TestOrderedWeakSet:
    def test_initialization(self):
        v1 = Ref(1)
        v2 = Ref(2)
        s = OrderedWeakSet([v1, v2, v1])
        assert len(s) == 2
        assert list(s) == [v1, v2]

    def test_add_discard(self):
        v1 = Ref(1)
        v2 = Ref(2)
        s = OrderedWeakSet()
        s.add(v1)
        s.add(v2)
        assert len(s) == 2
        assert list(s) == [v1, v2]
        s.add(v1)  # No repeat, order unchanged
        assert list(s) == [v1, v2]
        s.discard(v1)
        assert len(s) == 1
        assert v1 not in s
        s.discard(v1)  # No error

    def test_order_preservation(self):
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        s = OrderedWeakSet([v1, v3, v2])
        assert list(s) == [v1, v3, v2]
        s.discard(v3)
        assert list(s) == [v1, v2]
        s.add(v3)
        assert list(s) == [v1, v2, v3]

    def test_weak_reference_behavior(self):
        v1 = Ref(1)
        v2 = Ref(2)
        s = OrderedWeakSet([v1, v2])
        assert len(s) == 2
        del v1
        gc.collect()
        assert len(s) == 1
        assert list(s) == [v2]

    def test_set_operators(self):
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        s1 = OrderedWeakSet([v1, v2])
        s2 = OrderedWeakSet([v2, v3])

        # Union
        union = s1 | s2
        assert isinstance(union, OrderedWeakSet)
        assert list(union) == [v1, v2, v3]

        # Intersection
        inter = s1 & s2
        assert list(inter) == [v2]

        # Difference
        diff = s1 - s2
        assert list(diff) == [v1]

        # Symmetric Difference
        sym_diff = s1 ^ s2
        assert list(sym_diff) == [v1, v3]

    def test_clear_and_copy(self):
        v1 = Ref(1)
        v2 = Ref(2)
        s = OrderedWeakSet([v1, v2])
        s2 = s.copy()
        assert s == s2
        assert s is not s2
        s.clear()
        assert len(s) == 0
        assert len(s2) == 2

    def test_pop(self):
        v1 = Ref(1)
        v2 = Ref(2)
        s = OrderedWeakSet([v1, v2])
        val = s.pop()
        # pop() from a set is arbitrary, but from OrderedWeakSet it usually pops from the end
        # or at least it should be consistent.
        assert val in [v1, v2]
        assert len(s) == 1

    def test_repr(self):
        v1 = Ref(1)
        s = OrderedWeakSet([v1])
        assert "OrderedWeakSet" in repr(s)
        assert str(v1) in repr(s)

    def test_getitem(self):
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        s = OrderedWeakSet([v1, v2, v3])
        assert s[0] == v1
        assert s[1] == v2
        assert s[2] == v3
        assert s[:2] == [v1, v2]
        assert s[1:] == [v2, v3]
        with pytest.raises(IndexError):
            _ = s[3]


class TestBasic:
    """基础功能测试"""

    def test_weak_reference_behavior(self):
        """测试弱引用核心特性"""
        v1 = Ref(1)
        v2 = Ref(2)
        wl = WeakList([v1, v2, v1], noRepeat=True)
        # In new logic, duplicates move to end, so [v1, v2, v1] -> [v2, v1]
        assert wl.tuple == (v2, v1), f"初始化去重失败，预期 (v2, v1)，实际 {wl.tuple}"
        del v1  # 删除外部引用，弱引用失效
        assert wl.tuple == (v2,), f"弱引用失效失败，预期 (v2,)，实际 {wl.tuple}"

    def test_initialization_and_len(self):
        """测试基础初始化和长度"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl = WeakList([v1, v2, v3])
        assert len(wl) == 3, f"len 错误，预期 3，实际 {len(wl)}"
        assert wl.tuple == (
            v1,
            v2,
            v3,
        ), f"初始化错误，预期 (v1, v2, v3)，实际 {wl.tuple}"

    def test_append_extend(self):
        """测试append和extend方法"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl = WeakList([v1, v2])

        # 测试append
        v4 = Ref(4)
        wl.append(v4)
        assert wl.tuple == (v1, v2, v4), f"append错误，预期 (v1,v2,v4)，实际 {wl.tuple}"

        # 测试extend
        v5 = Ref(5)
        v6 = Ref(6)
        wl.extend([v5, v6])
        assert wl.tuple == (
            v1,
            v2,
            v4,
            v5,
            v6,
        ), f"extend错误，预期 (v1-v6)，实际 {wl.tuple}"


class TestInsert:
    """insert方法测试"""

    def test_insert_normal_position(self):
        """测试普通位置插入"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl = WeakList([v1, v3])
        wl.insert(1, v2)  # 在索引1插入v2
        assert wl.tuple == (
            v1,
            v2,
            v3,
        ), f"普通insert失败，预期 (v1,v2,v3)，实际 {wl.tuple}"

    def test_insert_negative_index(self):
        """测试负数索引插入"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        v4 = Ref(4)
        wl = WeakList([v1, v2, v3])
        wl.insert(-1, v4)  # 在倒数第一个位置插入
        assert wl.tuple == (
            v1,
            v2,
            v4,
            v3,
        ), f"负数索引insert失败，预期 (v1,v2,v4,v3)，实际 {wl.tuple}"

    def test_insert_out_of_bounds(self):
        """测试越界索引插入"""
        v1 = Ref(1)
        v2 = Ref(2)
        v5 = Ref(5)
        wl = WeakList([v1, v2])
        wl.insert(100, v5)  # 超出长度，插入到最后
        assert wl.tuple[-1].v == 5, (
            f"越界索引insert失败，最后一个元素应为5，实际 {wl.tuple[-1].v}"
        )

    def test_insert_no_repeat(self):
        """测试noRepeat模式下的插入去重"""
        v1 = Ref(1)
        v2 = Ref(2)
        wl_no_repeat = WeakList([v1, v2], noRepeat=True)
        wl_no_repeat.insert(1, v1)  # 插入重复项，移动到新位置
        assert wl_no_repeat.tuple == (
            v2,
            v1,
        ), f"noRepeat insert去重失败，预期 (v2,v1)，实际 {wl_no_repeat.tuple}"

    def test_insert_empty_list(self):
        """测试空列表插入"""
        v1 = Ref(1)
        wl_empty = WeakList()
        wl_empty.insert(0, v1)
        assert wl_empty.tuple == (v1,), (
            f"空列表insert失败，预期 (v1,)，实际 {wl_empty.tuple}"
        )


class TestPop:
    """pop方法测试"""

    def test_pop_default(self):
        """测试pop默认行为（弹出最后一个）"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl = WeakList([v1, v2, v3])
        popped = wl.pop()
        assert popped == v3, f"pop默认错误，预期 v3，实际 {popped}"
        assert wl.tuple == (v1, v2), f"pop后列表错误，预期 (v1,v2)，实际 {wl.tuple}"

    def test_pop_with_index(self):
        """测试指定索引pop"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl = WeakList([v1, v2, v3])
        popped = wl.pop(1)
        assert popped == v2, f"pop索引1错误，预期 v2，实际 {popped}"
        assert wl.tuple == (
            v1,
            v3,
        ), f"pop索引1后列表错误，预期 (v1,v3)，实际 {wl.tuple}"

    def test_pop_with_default_value(self):
        """测试pop带默认值"""
        v1 = Ref(1)
        v2 = Ref(2)
        wl = WeakList([v1, v2])
        default_val = Ref("default")
        popped = wl.pop(100, default=default_val)
        assert popped.v == "default", f"pop默认值错误，预期 default，实际 {popped.v}"

    def test_pop_invalid_index_without_default(self):
        """测试无效索引且无默认值时抛出异常"""
        v1 = Ref(1)
        v2 = Ref(2)
        wl = WeakList([v1, v2])
        with pytest.raises(IndexError):
            wl.pop(100)


class TestRemoveAndDelItem:
    """remove和__delitem__测试"""

    def test_remove(self):
        """测试remove方法"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl = WeakList([v1, v2, v3])
        wl.remove(v2)
        assert wl.tuple == (v1, v3), f"remove错误，预期 (v1,v3)，实际 {wl.tuple}"

    def test_delitem(self):
        """测试__delitem__方法"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl = WeakList([v1, v2, v3])
        del wl[1]  # 删除索引1
        assert wl.tuple == (v1, v3), f"__delitem__错误，预期 (v1,v3)，实际 {wl.tuple}"


class TestGetSetItem:
    """__getitem__和__setitem__测试"""

    def test_getitem(self):
        """测试__getitem__"""
        v1 = Ref(1)
        v2 = Ref(2)
        wl = WeakList([v1, v2])
        assert wl[0] == v1, f"__getitem__错误，预期 v1，实际 {wl[0]}"

    def test_setitem_normal(self):
        """测试__setitem__普通场景"""
        v1 = Ref(1)
        v2 = Ref(2)
        v7 = Ref(7)
        wl = WeakList([v1, v2])
        wl[1] = v7
        assert wl.tuple == (v1, v7), f"__setitem__错误，预期 (v1,v7)，实际 {wl.tuple}"

    def test_setitem_no_repeat(self):
        """测试noRepeat模式下的__setitem__去重"""
        v1 = Ref(1)
        v2 = Ref(2)
        wl_no_repeat = WeakList([v1, v2], noRepeat=True)
        wl_no_repeat[1] = v1
        assert wl_no_repeat.tuple == (v1,), (
            f"__setitem__去重错误，预期 (v1,)，实际 {wl_no_repeat.tuple}"
        )


class TestNoRepeat:
    """noRepeat功能测试"""

    def test_no_repeat_initialization(self):
        """测试初始化时的去重"""
        v1 = Ref(1)
        v8 = Ref(8)
        wl_no_repeat = WeakList([v1, v1, v8, v8], noRepeat=True)
        assert wl_no_repeat.tuple == (
            v1,
            v8,
        ), f"noRepeat初始化去重错误，预期 (v1,v8)，实际 {wl_no_repeat.tuple}"

    def test_append_move(self):
        """测试append重复项时移动到末尾"""
        v1 = Ref(1)
        v2 = Ref(2)
        wl = WeakList([v1, v2], noRepeat=True)
        wl.append(v1)
        assert wl.tuple == (v2, v1), f"append move失败, 预期 (v2, v1), 实际 {wl.tuple}"

    def test_insert_move(self):
        """测试insert重复项时移动到指定位置"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl = WeakList([v1, v2, v3], noRepeat=True)
        # 移动 v3 到索引 0
        wl.insert(0, v3)
        assert wl.tuple == (v3, v1, v2), (
            f"insert move失败, 预期 (v3, v1, v2), 实际 {wl.tuple}"
        )
        # 移动 v1 到索引 2 (末尾)
        wl.insert(2, v1)
        assert wl.tuple == (v3, v2, v1), (
            f"insert move失败, 预期 (v3, v2, v1), 实际 {wl.tuple}"
        )

    def test_dict_swap_sync_no_repeat_false(self):
        """测试 noRepeat=False 时 dict_swap 依然同步"""
        v1 = Ref(1)
        wl = WeakList([v1, v1], noRepeat=False)
        assert v1 in wl.dict_swap
        key = wl.dict_swap[v1]
        assert wl.dict[key] == v1

        # 删除一个
        wl.pop(0)
        assert v1 in wl.dict_swap
        assert len(wl) == 1

        # 删除最后一个
        wl.pop(0)
        assert v1 not in wl.dict_swap
        assert len(wl) == 0


class TestSortAndReverse:
    """sort和reverse方法测试"""

    def test_sort_ascending(self):
        """测试升序排序"""
        v1 = Ref(1)
        v7 = Ref(7)
        v9 = Ref(9)
        v10 = Ref(10)
        wl_sort = WeakList([v10, v7, v9, v1])
        wl_sort.sort(key=lambda x: x.v, reverse=False)
        assert wl_sort.tuple == (
            v1,
            v7,
            v9,
            v10,
        ), f"sort错误，预期 (v1,v7,v9,v10)，实际 {wl_sort.tuple}"

    def test_reverse(self):
        """测试反转"""
        v1 = Ref(1)
        v7 = Ref(7)
        v9 = Ref(9)
        v10 = Ref(10)
        wl_sort = WeakList([v1, v7, v9, v10])
        wl_sort.reverse()
        assert wl_sort.tuple == (
            v10,
            v9,
            v7,
            v1,
        ), f"reverse错误，预期 (v10,v9,v7,v1)，实际 {wl_sort.tuple}"


class TestMiscMethods:
    """其他方法测试（index, count, clear, copy, __contains__）"""

    def test_index(self):
        """测试index方法"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl_misc = WeakList([v1, v2, v2, v3])
        idx = wl_misc.index(v2)
        assert idx == 1, f"index错误，预期 1，实际 {idx}"

    def test_count(self):
        """测试count方法"""
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl_misc = WeakList([v1, v2, v2, v3])
        count = wl_misc.count(v2)
        assert count == 2, f"count错误，预期 2，实际 {count}"

    def test_copy(self):
        """测试copy方法"""
        v1 = Ref(1)
        v2 = Ref(2)
        wl_misc = WeakList([v1, v2])
        wl_copy = wl_misc.copy()
        assert wl_copy.tuple == wl_misc.tuple, (
            f"copy错误，预期 {wl_misc.tuple}，实际 {wl_copy.tuple}"
        )

    def test_clear(self):
        """测试clear方法"""
        v1 = Ref(1)
        v2 = Ref(2)
        wl_misc = WeakList([v1, v2])
        wl_misc.clear()
        assert wl_misc.tuple == (), f"clear错误，预期 ()，实际 {wl_misc.tuple}"

    def test_contains(self):
        """测试__contains__方法"""
        v1 = Ref(1)
        v7 = Ref(7)
        v9 = Ref(9)
        wl_contains = WeakList([v1, v7, v9])
        assert v1 in wl_contains, f"__contains__错误，预期 v1 在列表中"
        assert Ref(8) not in wl_contains, f"__contains__错误，预期 Value(8) 不在列表中"


class TestOperators:
    """运算符测试（+, +=, *, *=）"""

    def test_add_operator(self):
        """测试+运算符"""
        v1 = Ref(1)
        v7 = Ref(7)
        v9 = Ref(9)
        v10 = Ref(10)
        wl1 = WeakList([v1, v7])
        wl2 = WeakList([v9, v10])
        wl_add = wl1 + wl2
        assert wl_add.tuple == (
            v1,
            v7,
            v9,
            v10,
        ), f"+运算符错误，预期 (v1,v7,v9,v10)，实际 {wl_add.tuple}"

    def test_iadd_operator(self):
        """测试+=运算符"""
        v1 = Ref(1)
        v7 = Ref(7)
        v9 = Ref(9)
        v10 = Ref(10)
        wl1 = WeakList([v1, v7])
        wl2 = WeakList([v9, v10])
        wl1_bak = wl1.copy()
        wl1 += wl2
        assert wl1.tuple == (
            v1,
            v7,
            v9,
            v10,
        ), f"+=运算符错误，预期 (v1,v7,v9,v10)，实际 {wl1.tuple}"

    def test_mul_operator(self):
        """测试*运算符"""
        v1 = Ref(1)
        v7 = Ref(7)
        wl1_bak = WeakList([v1, v7])
        wl_mul = wl1_bak * 2
        assert wl_mul.tuple == (
            v1,
            v7,
            v1,
            v7,
        ), f"*运算符错误，预期 (v1,v7,v1,v7)，实际 {wl_mul.tuple}"

    def test_imul_operator(self):
        """测试*=运算符"""
        v1 = Ref(1)
        v7 = Ref(7)
        wl1_imul = WeakList([v1, v7])
        wl1_imul *= 2
        assert tuple(wl1_imul.dict.values()) == (
            v1,
            v7,
            v1,
            v7,
        ), f"*=运算符错误，预期 (v1,v7,v1,v7)，实际 {tuple(wl1_imul.dict.values())}"


class TestComparison:
    """比较运算符测试"""

    def test_comparison_operators(self):
        v1 = Ref(1)
        v2 = Ref(2)
        v3 = Ref(3)
        wl_a = WeakList([v1, v2])
        wl_b = WeakList([v1, v3])
        wl_c = WeakList([v1, v2])

        assert wl_a < wl_b, f"<运算符错误，预期 True，实际 {wl_a < wl_b}"
        assert wl_a == wl_c, f"==运算符错误，预期 True，实际 {wl_a == wl_c}"
        assert not (wl_a > wl_b), f">运算符错误，预期 False，实际 {wl_a > wl_b}"
        assert wl_a <= wl_c, f"<=运算符错误，预期 True，实际 {wl_a <= wl_c}"
        assert wl_a != wl_b, f"!=运算符错误，预期 True，实际 {wl_a != wl_b}"
