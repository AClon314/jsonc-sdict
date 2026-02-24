import inspect


def get_caller(up_level: int = 2):
    """
    获取调用栈中往上指定层数的调用信息
    Args:
        up_level: 往上查找的层数，默认2层
    Returns:
        dict: 调用信息字典，包含函数名、文件名、行号、调用代码行
    """
    # 获取完整调用栈（每个元素是栈帧信息元组）
    stack = inspect.stack()

    # 检查栈深度是否足够，避免索引越界
    if len(stack) <= up_level:
        return {"error": f"调用栈深度不足，无法查找往上{up_level}层的信息"}

    # 提取目标层级的栈帧信息
    target_frame = stack[up_level]
    frame, filename, lineno, func_name, code_context, index = target_frame

    # 整理返回信息
    caller_info = {
        # "py": filename,  # 调用文件路径
        "no": lineno,  # 调用行号
        "func": func_name,  # 调用函数名
        "line": code_context[0].strip() if code_context else "",  # 调用处的代码行
    }

    # 清理栈帧引用，避免内存泄漏
    del stack
    return caller_info
