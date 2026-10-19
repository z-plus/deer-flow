from langchain_core.tools import tool


@tool
def add(a: int, b: int) -> int:
    """将两个整数相加并返回结果。"""

    return a + b
