"""Security policy and static analysis for script automation sandbox."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import List, Optional

from ...core.global_state import get_script_sandbox_dir

# ── 黑名单模块 ──────────────────────────────────────────
# 这些模块在包装器注入层会被禁止导入
BLOCKED_MODULES: List[str] = [
    "subprocess",
    "ctypes",
    "_ctypes",
    "winreg",
    "_winreg",
    "socket",
    "multiprocessing",
]

# ── 运行时限制 ──────────────────────────────────────────
MAX_EXECUTION_TIME: int = 60        # 脚本最大执行时间（秒）
MAX_OUTPUT_CHARS: int = 5000        # 输出截断长度

# ── 静态分析：危险模式检测 ──────────────────────────────
DANGEROUS_PATTERNS: List[str] = [
    "eval(",
    "exec(",
    "compile(",
    "__import__(",
]


def validate_and_resolve_sandbox_dir(path_str: str) -> Path:
    """验证用户指定的路径字符串，确保其存在且是一个目录。

    用于 API 层接收用户输入路径时的校验。与 ``get_sandbox_dir()`` 不同，
    此函数不依赖 global_state，而是直接校验传入的路径。

    Args:
        path_str: 用户输入的目录路径（绝对路径）。

    Returns:
        规范化后的 Path 对象。

    Raises:
        FileNotFoundError: 路径不存在。
        NotADirectoryError: 路径存在但不是目录。
        ValueError: 路径为空或非法。
    """
    if not path_str or not path_str.strip():
        raise ValueError("路径不能为空")

    resolved = Path(path_str.strip()).resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"路径不存在: {resolved}")

    if not resolved.is_dir():
        raise NotADirectoryError(f"路径不是目录: {resolved}")

    return resolved


def get_sandbox_dir() -> Path:
    """获取当前沙箱工作目录的 Path 对象。

    Returns:
        沙箱目录的 Path。

    Raises:
        ValueError: 如果沙箱目录未设置。
    """
    sandbox_dir = get_script_sandbox_dir()
    if not sandbox_dir:
        raise ValueError(
            "Script sandbox directory is not set. "
            "Please call set_script_sandbox_dir(path) first."
        )
    return Path(sandbox_dir).resolve()


def validate_path(target_path: str, sandbox_dir: Optional[Path] = None) -> str:
    """验证目标路径是否在沙箱目录范围内。

    防止路径穿越（../../）和绝对路径越界访问。

    Args:
        target_path: 要验证的目标路径（相对或绝对）。
        sandbox_dir: 沙箱目录，默认从 global_state 获取。

    Returns:
        规范化后的绝对路径。

    Raises:
        PermissionError: 如果路径不在沙箱目录范围内。
    """
    if sandbox_dir is None:
        sandbox_dir = get_sandbox_dir()

    sandbox_dir = Path(sandbox_dir).resolve()
    resolved = Path(sandbox_dir, target_path).resolve()

    if not str(resolved).startswith(str(sandbox_dir)):
        raise PermissionError(
            f"访问被拒绝: '{target_path}' 不在沙箱工作目录范围内 "
            f"({sandbox_dir})"
        )

    return str(resolved)


def scan_for_dangerous_patterns(code: str) -> List[dict]:
    """静态扫描脚本代码中的危险模式。

    检测黑名单模块导入、eval/exec 调用等。

    Args:
        code: Python 脚本源代码。

    Returns:
        安全问题列表，每个元素为 {"severity": ..., "line": ..., "message": ...}。
    """
    issues: List[dict] = []

    # 1. AST 级别的检测
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{"severity": "error", "line": 0, "message": f"语法错误: {e}"}]

    for node in ast.walk(tree):
        # 检测危险 import
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in BLOCKED_MODULES:
                    issues.append({
                        "severity": "danger",
                        "line": getattr(node, "lineno", 0),
                        "message": f"导入了被安全策略禁止的模块: '{alias.name}'",
                    })

        # 检测危险 from ... import
        if isinstance(node, ast.ImportFrom):
            if node.module in BLOCKED_MODULES:
                issues.append({
                    "severity": "danger",
                    "line": getattr(node, "lineno", 0),
                    "message": f"导入了被安全策略禁止的模块: '{node.module}'",
                })

        # 检测 eval / exec 调用
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec", "compile"):
                issues.append({
                    "severity": "critical",
                    "line": getattr(node, "lineno", 0),
                    "message": f"检测到危险函数调用: '{node.func.id}()'，将在运行时被阻止",
                })

    return issues
