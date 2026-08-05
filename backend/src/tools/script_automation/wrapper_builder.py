"""Sandbox wrapper builder — the core security mechanism.

生成一个 Python 包装脚本，在 exec 用户脚本之前注入安全层。
注入点共 9 层：
  1. builtins.__import__ → 模块黑名单 + 替换 os/shutil
  2. os.rename / os.replace → 路径验证
  3. os.system / os.popen → 禁用（禁止 shell 命令执行）
  4. os.open / os.mkdir / os.makedirs / os.chdir → 路径验证
     os.remove / os.unlink / os.rmdir / os.removedirs → 移至 .trash 回收站
  5. os.symlink / os.link / os.truncate / os.removedirs → 路径验证
  6. shutil.move → 路径验证（因 shutil 内部引用原始 os，无法被策略 4/5 覆盖）
     shutil.rmtree → 移至 .trash 回收站
  7. builtins.eval → 禁用
  8. builtins.open → 写模式路径验证
  9. sys.addaudithook → 统一兜底（3.8+），捕获 open / os.system / os.popen / subprocess 等
  +  builtins.input → 自动返回空（防止脚本挂起）
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import List

from .safety import BLOCKED_MODULES


def build_wrapper(script_path: Path, sandbox_dir: Path) -> str:
    """构建沙箱包装器脚本源码。

    Args:
        script_path: 用户脚本的绝对路径。
        sandbox_dir: 沙箱工作目录的绝对路径。

    Returns:
        完整的包装器 Python 脚本源码。
    """
    blocked_modules_repr = repr(BLOCKED_MODULES)
    sandbox_dir_str = str(sandbox_dir.resolve())
    script_path_str = str(script_path.resolve())

    # 使用 textwrap.dedent 来保持缩进整洁
    return textwrap.dedent(f'''"""Sandbox wrapper — auto-generated."""
import sys as _sys
import builtins as _builtins
import os as _real_os
import shutil as _real_shutil
import uuid as _uuid

# ================================================================
# 🛡️ 安全策略 1：模块导入黑名单 + os/shutil 替换
# ================================================================

_BLOCKED_MODULES = {blocked_modules_repr}
_SANDBOX_DIR = {repr(sandbox_dir_str)}


def _safe_import(name, *args, **kwargs):
    """劫持 __import__：阻止黑名单模块，替换 os 和 shutil。"""
    if name in _BLOCKED_MODULES:
        raise ImportError(
            f"安全策略禁止导入模块: '{{name}}'"
        )
    if name == "os":
        return _PATCHED_OS
    if name == "shutil":
        return _PATCHED_SHUTIL
    return _original_import(name, *args, **kwargs)


_original_import = _builtins.__import__
_builtins.__import__ = _safe_import


# ================================================================
# 🛡️ 安全策略 2：路径验证
# ================================================================

def _validate_path(target_path: str) -> str:
    """验证路径是否在沙箱目录内。防止路径穿越和绝对路径越界。"""
    resolved = _real_os.path.abspath(_real_os.path.join(_real_os.getcwd(), target_path))
    if not resolved.startswith(_SANDBOX_DIR):
        raise PermissionError(
            f"访问被拒绝: '{{target_path}}' 不在沙箱工作目录范围内"
        )
    return resolved


def _move_to_trash(path: str) -> None:
    """将文件/目录移至 .trash 目录而非真正删除。"""
    trash_dir = _real_os.path.join(_SANDBOX_DIR, ".trash")
    _real_os.makedirs(trash_dir, exist_ok=True)
    base = _real_os.path.basename(path.rstrip(_real_os.sep))
    uid = _uuid.uuid4().hex[:12]
    dest = _real_os.path.join(trash_dir, f"{{base}}_{{uid}}")
    _real_shutil.move(path, dest)


# ================================================================
# 🛡️ 安全策略 3：修补 os 模块
# ================================================================

_PATCHED_OS = type(_sys)("os")
_PATCHED_OS.__dict__.update(_real_os.__dict__)


def _safe_rename(src: str, dst: str) -> None:
    """安全的 os.rename — 验证源和目标路径。"""
    _validate_path(src)
    _validate_path(dst)
    return _real_os.rename(src, dst)


def _safe_replace(src: str, dst: str) -> None:
    """安全的 os.replace — 验证源和目标路径。"""
    _validate_path(src)
    _validate_path(dst)
    return _real_os.replace(src, dst)


_PATCHED_OS.rename = _safe_rename
_PATCHED_OS.replace = _safe_replace


# ================================================================
# 🛡️ 安全策略 4：禁用命令执行
# ================================================================

# 禁止 os.system — 执行 shell 命令
_PATCHED_OS.system = None
# 禁止 os.popen — 执行 shell 命令并读取输出
_PATCHED_OS.popen = None


# ================================================================
# 🛡️ 安全策略 5：修补更多 os 文件操作 — 路径验证
# ================================================================


def _safe_os_open(path: str, flags: int, mode: int = 0o777, *args, **kwargs) -> int:
    """安全的 os.open — 验证路径后调用原始 os.open。"""
    _validate_path(path)
    return _real_os.open(path, flags, mode, *args, **kwargs)


def _safe_os_remove(path: str) -> None:
    """安全的 os.remove — 移至 .trash 而非真正删除。"""
    _validate_path(path)
    return _move_to_trash(path)


def _safe_os_unlink(path: str) -> None:
    """安全的 os.unlink — 移至 .trash 而非真正删除。"""
    _validate_path(path)
    return _move_to_trash(path)


def _safe_os_rmdir(path: str) -> None:
    """安全的 os.rmdir — 移至 .trash 而非真正删除。"""
    _validate_path(path)
    return _move_to_trash(path)


def _safe_os_mkdir(path: str, mode: int = 0o777) -> None:
    """安全的 os.mkdir — 验证路径。"""
    _validate_path(path)
    return _real_os.mkdir(path, mode)


def _safe_os_makedirs(path: str, mode: int = 0o777, exist_ok: bool = False) -> None:
    """安全的 os.makedirs — 验证路径。"""
    _validate_path(path)
    return _real_os.makedirs(path, mode, exist_ok)


def _safe_os_chdir(path: str) -> None:
    """安全的 os.chdir — 只允许切换到沙箱内的目录。"""
    _validate_path(path)
    return _real_os.chdir(path)


_PATCHED_OS.open = _safe_os_open
_PATCHED_OS.remove = _safe_os_remove
_PATCHED_OS.unlink = _safe_os_unlink
_PATCHED_OS.rmdir = _safe_os_rmdir
_PATCHED_OS.mkdir = _safe_os_mkdir
_PATCHED_OS.makedirs = _safe_os_makedirs
_PATCHED_OS.chdir = _safe_os_chdir


# ================================================================
# 🛡️ 安全策略 6：修补更多 os 操作 — 链接/截断
# ================================================================


def _safe_os_symlink(src: str, dst: str, target_is_directory: bool = False, *, dir_fd=None) -> None:
    """安全的 os.symlink — 验证链接创建路径在沙箱内。"""
    _validate_path(dst)
    return _real_os.symlink(src, dst, target_is_directory, dir_fd=dir_fd)


def _safe_os_link(src: str, dst: str, *, src_dir_fd=None, dst_dir_fd=None) -> None:
    """安全的 os.link — 验证源和目标的路径。"""
    _validate_path(src)
    _validate_path(dst)
    return _real_os.link(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)


def _safe_os_truncate(path: str, length: int) -> None:
    """安全的 os.truncate — 验证路径。"""
    _validate_path(path)
    return _real_os.truncate(path, length)


def _safe_os_removedirs(path: str) -> None:
    """安全的 os.removedirs — 移至 .trash 而非真正删除。"""
    _validate_path(path)
    return _move_to_trash(path)


_PATCHED_OS.symlink = _safe_os_symlink
_PATCHED_OS.link = _safe_os_link
_PATCHED_OS.truncate = _safe_os_truncate
_PATCHED_OS.removedirs = _safe_os_removedirs


# ================================================================
# 🛡️ 安全策略 7：修补 shutil 模块
# ================================================================

_real_shutil = _original_import("shutil")
_PATCHED_SHUTIL = type(_sys)("shutil")
_PATCHED_SHUTIL.__dict__.update(_real_shutil.__dict__)


def _safe_shutil_move(src: str, dst: str) -> None:
    """安全的 shutil.move — 验证源和目标路径。"""
    _validate_path(src)
    _validate_path(dst)
    return _real_shutil.move(src, dst)


_PATCHED_SHUTIL.move = _safe_shutil_move


def _safe_shutil_rmtree(path: str, ignore_errors: bool = False, onerror=None, *, onexc=None) -> None:
    """安全的 shutil.rmtree — 移至 .trash 而非真正删除。"""
    _validate_path(path)
    return _move_to_trash(path)


_PATCHED_SHUTIL.rmtree = _safe_shutil_rmtree


# ================================================================
# 🛡️ 安全策略 8：修补内置函数
# ================================================================

# 禁用 eval
_builtins.eval = None

# 修补 open — 只读模式不受限，写模式需要路径验证
_original_open = _builtins.open


def _safe_open(file, mode="r", *args, **kwargs):
    """安全的 open — 写/追加/创建模式需要路径验证。"""
    if mode and any(c in mode for c in ("w", "a", "x", "+")):
        _validate_path(file)
    return _original_open(file, mode, *args, **kwargs)


_builtins.open = _safe_open

# 禁止 input（防止脚本因等待输入而挂起）
_builtins.input = lambda prompt="": ""


# ================================================================
# 🛡️ 安全策略 9：Python Audit Hook（3.8+ 统一兜底）
# ================================================================


def _sandbox_audit_hook(event: str, args: tuple) -> None:
    """统一拦截沙箱外的文件访问和命令执行。

    覆盖 builtins.open、os.system、os.popen、subprocess.Popen 等。
    Python 3.7 及以下静默跳过（hasattr 保护），靠 per-function patch 继续防护。
    """
    if event == "open":
        # 捕获所有 open() 调用（builtins.open、io.open 等）
        file = args[0] if args else ""
        _validate_path(file)
    elif event in ("os.system", "os.popen", "subprocess.Popen"):
        raise RuntimeError(f"安全策略禁止在沙箱中执行命令: {{event}}")


if hasattr(_sys, "addaudithook"):
    _sys.addaudithook(_sandbox_audit_hook)


# ================================================================
# ▶️ 执行用户脚本
# ================================================================

_script_path = {repr(script_path_str)}
with open(_script_path, encoding="utf-8") as _f:
    _code = _f.read()

# 使用 exec 执行用户脚本（将 __name__ 设为 __main__）
_global_vars = {{"__name__": "__main__", "__file__": _script_path}}
exec(_code, _global_vars)
''')


def _default_blocked_modules() -> List[str]:
    """返回默认的黑名单模块列表，供安全策略参考。"""
    return BLOCKED_MODULES
