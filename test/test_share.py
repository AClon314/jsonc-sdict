from jsonc_sdict.share import in_range


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
