import inspect


def get_caller(*_name_: str, Slice=slice(0, 3)) -> list[dict]:
    """
    获取调用栈中指定模块内往上指定层数的调用信息
    Args:
        _name_:模块名
        Slice:默认截到前3层
    Returns:
        tuple[dict]: {func, code, file, lineno}
    """
    caller_info = []
    # 获取完整调用栈（frame对象列表）
    frames = inspect.stack(context=1)

    for name in _name_:
        for f in frames:
            # 提取frame对象和相关信息
            frame = f.frame
            # 过滤：只保留指定模块内的调用
            # 先获取当前frame对应的模块名
            frame_module = inspect.getmodule(frame)
            if frame_module is None or frame_module.__name__ != name:
                continue

            # filename = f.filename
            lineno = f.lineno
            function = f.function
            # 获取调用行的代码（处理换行/空行）
            code = f.code_context[0].strip() if f.code_context else ""

            # 整理信息（兼容不同Python版本，避免属性缺失）
            info = {
                "lineno": lineno,
                "func": function,
                "code": code,
                # "file": filename,
            }
            caller_info.append(info)

            # 必须清理frame，避免内存泄漏
            del frame

    return caller_info[Slice]


# ------------------- 测试示例 -------------------
def test_func1():
    # 调用get_caller，获取当前模块内的调用信息
    caller = get_caller(__name__)
    print("test_func1调用信息:", caller)


def test_func2():
    test_func1()  # 嵌套调用，测试栈层数


if __name__ == "__main__":
    test_func2()
