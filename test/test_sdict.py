import pytest
from jsonc_sdict.sdict import sdict as SDict
from share import get_caller


class sdict(SDict):
    def __getattribute__(self, name: str):
        if name not in ("v", "data", "ref"):  # avoid recursion
            # try:
            #     data = object.__getattribute__(self, "data") # avoid recursion
            # except AttributeError:
            #     data = self
            # try:
            #     ref = object.__getattribute__(self, "ref")
            # except AttributeError:
            #     ref = self
            print(self, *get_caller("jsonc_sdict.sdict", "test_sdict"), sep="\t")
        return super().__getattribute__(name)


def test_init_basic():
    """测试基本初始化"""
    d = sdict({"a": 1, "b": 2})
    assert d["a"] == 1
    assert d["b"] == 2
    assert isinstance(d, sdict)


def test_init_ref():
    """测试 ref 参数"""
    data = [1, 2, 3]
    d = sdict(ref=data)
    assert d.ref == data


def test_nested_access():
    """测试多层嵌套取值"""
    d = sdict(
        {
            "user": {
                "info": {
                    "name": "张三",
                    "address": {"city": "深圳", "areas": ["南山", "宝安"]},
                }
            }
        }
    )

    # 字符串路径
    assert d["user", "info", "name"] == "张三"
    # 混合索引 (字符串 + 整数)
    assert d["user", "info", "address", "areas", 0] == "南山"
    assert d["user", "info", "address", "areas", 1] == "宝安"
    # 自动包装子映射为 sdict
    assert isinstance(d["user", "info"], sdict)
    assert d["user", "info"]["name"] == "张三"


def test_slice_access():
    """测试切片访问 (基于 items_flat)"""
    d = sdict({"a": {"b": {"c": 1}}, "x": {"y": 2}})
    # depth=0 是 root 自身 (sdict 设计中 dfs 会 yield self)
    # depth=1 是 a, x
    # depth=2 是 b, y
    # depth=3 是 c

    # 获取 depth 为 1 的子节点 (a, x)
    items = d[1:2]
    assert len(items) == 2
    assert all(isinstance(i, sdict) for i in items)
    assert set(i.keypath[-1][0] for i in items) == {"a", "x"}


def test_flat_iteration():
    """测试扁平化迭代"""
    data = {"a": 1, "b": {"c": 2, "d": [3, 4]}}
    d = sdict(data)

    # items_flat
    flat_items = list(d.items_flat())
    # 预期节点:
    # 1. Root (depth 0)
    # 2. b (depth 1)
    # 3. d (depth 2) - 如果 List=True

    # 验证 depth
    depths = [v.depth for _, v in flat_items]
    assert 0 in depths
    assert 1 in depths

    # keys_flat
    keys = list(d.keys_flat())
    assert any(k == () for k in keys)  # root
    assert any(k == (["b"],) for k in keys)


def test_metadata():
    """测试元数据 (depth, parent, keypath)"""
    d = sdict({"a": {"b": 1}})

    root = d
    child_a = d["a"]

    assert root.depth == 0
    assert child_a.depth == 1
    assert child_a.parent[0] is root
    assert child_a.keypath == (["a"],)


def test_errors():
    """测试异常处理"""
    d = sdict({"a": [1, 2]})

    with pytest.raises(KeyError):
        _ = d["non_existent"]

    with pytest.raises(KeyError):
        _ = d["a", 5]

    with pytest.raises(KeyError):
        # a 是 list，但在 sdict 中被包装为 UserDict，使用无效 key 会报 KeyError
        _ = d["a", "invalid_key"]


def test_rebuild():
    """测试 rebuild 和缓存刷新"""
    d = sdict({"a": {"b": 1}})
    child = d["a"]

    # 修改原始数据 (避开 sdict 封装，直接改 data)
    d.data["a"]["c"] = 2

    # 此时 rebuild
    d.rebuild()

    # 验证新键是否存在
    assert d["a", "c"] == 2


def test_childkeys():
    """测试 childkeys 缓存属性"""
    d = sdict({"a": 1, "b": {"c": 2}})

    # 第一次访问触发缓存
    ck = d.childkeys
    assert len(ck) >= 1
    assert any(isinstance(x, sdict) for x in ck)

    # 刷新缓存测试 (模拟 rebuild 中的逻辑)
    del d.childkeys
    assert "childkeys" not in d.__dict__
    new_ck = d.childkeys
    assert len(new_ck) >= 1
