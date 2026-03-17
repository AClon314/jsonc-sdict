from jsonc_sdict.share import in_range, len_slice


def test_in_range():
    # 测试无步长场景
    assert in_range(2, slice(0, 5))
    assert not in_range(5, slice(0, 5))

    # 测试有步长+stop=None场景
    assert in_range(3, slice(1, None, 2))  # 1,3,5...
    assert not in_range(4, slice(1, None, 2))

    # 测试负步长场景
    assert in_range(4, slice(5, 0, -1))  # 5,4,3,2,1
    assert not in_range(0, slice(5, 0, -1))

    # 测试异常场景（验证报错）
    try:
        in_range(1, slice(0, 5, 0))
    except ValueError as e:
        assert str(e) == "slice step cannot be zero"


def test_valid_len():
    # 测试1：基础正向切片
    assert len_slice(10, slice(2, 8, 2)) == 3  # [2,4,6] → 长度3
    # 测试2：负数索引（修正stop为5，使切片包含索引2、3、4）
    assert len_slice(5, slice(-3, 5)) == 3  # 索引2,3,4 → 长度3
    # 测试3：反向切片
    assert len_slice(10, slice(8, 2, -2)) == 3  # [8,6,4] → 长度3
    # 测试4：超出范围的切片
    assert len_slice(5, slice(10, 20)) == 0  # 无有效元素 → 长度0
    # 测试5：默认切片（取全部）
    assert len_slice(7, slice(None)) == 7  # 取全部元素 → 长度7
    # 测试6：空序列
    assert len_slice(0, slice(1, 3)) == 0  # 原序列为空 → 长度0
