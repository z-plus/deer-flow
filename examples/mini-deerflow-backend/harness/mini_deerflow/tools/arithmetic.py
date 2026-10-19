from langchain_core.tools import tool


@tool
def add(a: int, b: int) -> int:
    """将两个整数相加并返回结果。"""

    return a + b

@tool(parse_docstring=True)
def multiply(a: int, b: int) -> int:
    """计算两个整数的乘积。

    Args:
        a: 第一个整数。
        b: 第二个整数。

    Returns:
        两个整数的乘积。
    """
    return a * b
