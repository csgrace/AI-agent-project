"""Sandbox virtual environment manager.

自动在沙箱工作目录下创建和管理 .venv/ 虚拟环境。
所有 pip 操作在沙箱外部执行（@tool 函数直接调用 subprocess），不受模块黑名单限制。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .safety import get_sandbox_dir, MAX_EXECUTION_TIME


def ensure_sandbox_venv() -> Path:
    """确保沙箱目录下存在可用的 .venv/ 虚拟环境。

    如果 .venv/ 不存在，自动创建（使用与当前进程相同的 Python 解释器）。

    Returns:
        .venv 中 python.exe 的绝对路径。
    """
    sandbox_dir = get_sandbox_dir()
    venv_dir = sandbox_dir / ".venv"

    if not _is_valid_venv(venv_dir):
        _create_venv(sandbox_dir, venv_dir)

    return _get_venv_python(venv_dir)


def _is_valid_venv(venv_dir: Path) -> bool:
    """检查 .venv/ 是否是一个可用的虚拟环境。"""
    python_path = _get_venv_python(venv_dir)
    return python_path.exists()


def _get_venv_python(venv_dir: Path) -> Path:
    """获取 .venv 中 python 解释器的路径（跨平台）。"""
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _get_venv_pip(venv_dir: Path) -> Path:
    """获取 .venv 中 pip 的路径（跨平台）。"""
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "pip"


def _create_venv(sandbox_dir: Path, venv_dir: Path) -> None:
    """在沙箱目录中创建虚拟环境。"""
    print(f"[sandbox_env] Creating .venv in {sandbox_dir}...")
    result = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        cwd=str(sandbox_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"创建虚拟环境失败:\n{result.stderr}"
        )
    print(f"[sandbox_env] .venv created at {venv_dir}")


def install_package(package_name: str) -> str:
    """在沙箱的虚拟环境中安装 Python 包。

    此函数在沙箱外部执行（由 @tool 直接调用），可以正常使用 subprocess。

    Args:
        package_name: 包名（如 "requests", "pandas==2.0.0"）。

    Returns:
        pip install 的输出。

    Raises:
        RuntimeError: 如果安装失败。
    """
    sandbox_dir = get_sandbox_dir()
    venv_dir = sandbox_dir / ".venv"

    # 确保 venv 存在
    if not _is_valid_venv(venv_dir):
        raise RuntimeError(
            "沙箱虚拟环境尚未初始化。请先执行任意脚本（将自动创建 .venv）或手动创建。"
        )

    pip_path = _get_venv_pip(venv_dir)

    print(f"[sandbox_env] Installing '{package_name}' into {venv_dir}...")
    result = subprocess.run(
        [str(pip_path), "install", package_name],
        cwd=str(sandbox_dir),
        capture_output=True,
        text=True,
        timeout=MAX_EXECUTION_TIME,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"安装 '{package_name}' 失败:\n{result.stderr}"
        )

    # 截断过长的 pip 输出（保留尾部）
    output = result.stdout
    if len(output) > MAX_OUTPUT_CHARS:
        output = f"... (安装输出已截断，共 {len(output)} 字符，仅显示末尾 {MAX_OUTPUT_CHARS} 字符)\n" + output[-MAX_OUTPUT_CHARS:]
    return output


def list_installed_packages() -> str:
    """列出沙箱虚拟环境中已安装的所有包。

    Returns:
        pip list 的输出。

    Raises:
        RuntimeError: 如果虚拟环境不存在。
    """
    sandbox_dir = get_sandbox_dir()
    venv_dir = sandbox_dir / ".venv"

    if not _is_valid_venv(venv_dir):
        return "沙箱虚拟环境尚未初始化。请先执行任意脚本。"

    pip_path = _get_venv_pip(venv_dir)

    result = subprocess.run(
        [str(pip_path), "list", "--format=columns"],
        cwd=str(sandbox_dir),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout
