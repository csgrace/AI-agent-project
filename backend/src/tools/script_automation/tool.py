"""@tool functions for script automation — the main interface for the LLM agent.

提供 10 个工具，分为四组：
  - 脚本管理：list_scripts, create_script, read_script, update_script, delete_script
  - 文件系统查看：list_sandbox_directory (ls), read_sandbox_file (cat)
  - 包管理：install_sandbox_package, list_sandbox_packages
  - 执行：execute_script

所有操作基于当前沙箱工作目录（由 global_state.SCRIPT_SANDBOX_DIR 指定）。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from langchain.tools import ToolRuntime, tool

from .schemas import (
    CreateScriptParams,
    ListDirectoryParams,
    ReadFileParams,
    ReadScriptParams,
    UpdateScriptParams,
    DeleteScriptParams,
    ListScriptsParams,
    ExecuteScriptParams,
    InstallPackageParams,
)
from . import storage
from . import executor
from . import sandbox_env
from .safety import scan_for_dangerous_patterns, get_sandbox_dir, validate_path


def _ok_response(action: str, **extra: Any) -> str:
    """构建标准成功响应。"""
    result: Dict[str, Any] = {"ok": True, "action": action}
    result.update(extra)
    return json.dumps(result, ensure_ascii=False)


def _error_response(action: str, message: str) -> str:
    """构建标准错误响应。"""
    return json.dumps(
        {"ok": False, "action": action, "error": message},
        ensure_ascii=False,
    )


# ====================================================================
# 脚本管理
# ====================================================================


@tool
def create_script(params: CreateScriptParams) -> str:
    """创建一个新的自动化 Python 脚本，保存在 {sandbox_dir}/.scripts/ 中。

    脚本创建后可通过 execute_script 工具执行。
    如果需要安装第三方包，先调用 install_sandbox_package。

    Args:
        params: 包含 name（脚本名，不含.py）、content（Python代码）、
                description（描述）、category（分类，如 file_operation）。

    Returns:
        JSON: {"ok": true, "action": "create", "name": "..."} 或错误信息。
    """
    try:
        # 预扫描危险模式
        issues = scan_for_dangerous_patterns(params.content)
        warnings = [iss for iss in issues if iss["severity"] in ("danger", "critical")]

        msg = storage.create_script_file(
            name=params.name,
            content=params.content,
            description=params.description,
            category=params.category,
        )

        response = _ok_response("create", name=params.name, message=msg)
        if warnings:
            # 将安全警告附加到响应中
            warning_lines = []
            for w in warnings:
                warning_lines.append(f"  ⚠️ 第 {w['line']} 行: {w['message']}")
            response_data = json.loads(response)
            response_data["security_warnings"] = warning_lines
            response = json.dumps(response_data, ensure_ascii=False)

        return response

    except ValueError as e:
        return _error_response("create", str(e))


@tool
def read_script(params: ReadScriptParams) -> str:
    """查看指定脚本的源代码和元数据。

    Args:
        params: 包含 name（脚本名）。

    Returns:
        JSON: 包含脚本的 content 和 metadata。
    """
    try:
        content, metadata = storage.read_script_file(params.name)
        return _ok_response(
            "read",
            name=params.name,
            content=content,
            metadata=metadata,
        )
    except ValueError as e:
        return _error_response("read", str(e))


@tool
def update_script(params: UpdateScriptParams) -> str:
    """更新已有脚本的内容或元信息（描述、分类）。

    只传入需要修改的字段，不传的字段保持原样。

    Args:
        params: 包含 name 和可选的 content / description / category。

    Returns:
        JSON: 更新结果。
    """
    try:
        msg = storage.update_script_file(
            name=params.name,
            content=params.content,
            description=params.description,
            category=params.category,
        )

        # 如果更新了内容，重新扫描安全风险
        warnings = []
        if params.content is not None:
            issues = scan_for_dangerous_patterns(params.content)
            warnings = [iss for iss in issues if iss["severity"] in ("danger", "critical")]

        response = _ok_response("update", name=params.name, message=msg)
        if warnings:
            response_data = json.loads(response)
            warning_lines = []
            for w in warnings:
                warning_lines.append(f"  ⚠️ 第 {w['line']} 行: {w['message']}")
            response_data["security_warnings"] = warning_lines
            response = json.dumps(response_data, ensure_ascii=False)

        return response

    except ValueError as e:
        return _error_response("update", str(e))


@tool
def delete_script(params: DeleteScriptParams) -> str:
    """从当前沙箱中删除指定的自动化脚本。

    此操作不可逆。脚本文件将被永久删除。

    Args:
        params: 包含 name（脚本名）。

    Returns:
        JSON: 删除结果。
    """
    try:
        msg = storage.delete_script_file(params.name)
        return _ok_response("delete", name=params.name, message=msg)
    except ValueError as e:
        return _error_response("delete", str(e))


@tool
def list_scripts(params: ListScriptsParams) -> str:
    """列出当前沙箱中的所有自动化脚本及其描述。

    返回格式化的列表，包含每个脚本的名称、分类、描述和上次更新时间。

    Args:
        params: 无参数（自动使用当前沙箱目录）。

    Returns:
        JSON: { "ok": true, "action": "list", "scripts": [...], "summary": "..." }。
    """
    try:
        formatted = storage.list_script_files()

        # 同时返回结构化数据
        scripts_dir = storage._get_scripts_dir()
        metadata = storage._load_metadata()
        script_list = []
        for f in scripts_dir.iterdir():
            if f.suffix == ".py" and f.name != "__init__.py":
                name = f.stem
                meta = metadata.get(name, {})
                script_list.append({
                    "name": name,
                    "description": meta.get("description", ""),
                    "category": meta.get("category", "general"),
                    "updated_at": meta.get("updated_at", ""),
                })
        script_list.sort(key=lambda x: x["name"])

        return _ok_response(
            "list",
            scripts=script_list,
            summary=formatted,
        )
    except ValueError as e:
        return _error_response("list", str(e))


# ====================================================================
# 包管理
# ====================================================================


@tool
def install_sandbox_package(params: InstallPackageParams) -> str:
    """在沙箱的 Python 虚拟环境中安装一个第三方包。

    安装后，沙箱中的脚本就可以 import 这个包了。
    例如：install_sandbox_package("requests") → 脚本里可 import requests。
    支持指定版本：install_sandbox_package("pandas==2.0.0")

    此操作在沙箱外部执行（安全），不受模块黑名单限制。

    Args:
        params: 包含 package_name（包名，支持版本号）。

    Returns:
        JSON: pip install 的输出结果。
    """
    try:
        output = sandbox_env.install_package(params.package_name)
        return _ok_response(
            "install_package",
            package=params.package_name,
            output=output.strip(),
        )
    except (ValueError, RuntimeError) as e:
        return _error_response("install_package", str(e))


@tool
def list_sandbox_packages() -> str:
    """列出沙箱虚拟环境中已安装的所有 Python 包。

    使用 pip list 获取当前 .venv 中的包列表。

    Args:
        无参数。

    Returns:
        JSON: 包含包列表和原始 pip list 输出。
    """
    try:
        output = sandbox_env.list_installed_packages()
        return _ok_response("list_packages", pip_list=output.strip())
    except ValueError as e:
        return _error_response("list_packages", str(e))


# ====================================================================
# 脚本执行
# ====================================================================


@tool
def execute_script(runtime: ToolRuntime, params: ExecuteScriptParams) -> str:
    """在沙箱隔离环境中执行指定的 Python 自动化脚本。

    安全特性:
      - 运行在沙箱的 .venv 虚拟环境中
      - 危险模块（subprocess, ctypes 等）被禁止导入
      - 文件写入/重命名操作限制在沙箱目录范围内
      - 脚本最多执行 60 秒，超时自动终止
      - 可通过 install_sandbox_package 预先安装依赖
      - 支持流式输出：脚本的 stdout/stderr 会通过 stream_writer 实时推送

    使用前请确保：
      1. 已通过 set_script_sandbox_dir() 设置沙箱目录
      2. 脚本已通过 create_script 创建
      3. 所需的第三方包已通过 install_sandbox_package 安装

    Args:
        runtime: LangGraph 运行时（自动注入，对模型透明）。
        params: 包含 name（脚本名）和可选的 args（命令行参数）。

    Returns:
        JSON: { "ok": bool, "stdout": str, "stderr": str, "returncode": int }。
    """
    try:
        writer = runtime.stream_writer if runtime else None

        # 生成唯一 execution_id（uuid4 短格式 8 位十六进制）
        execution_id = uuid.uuid4().hex[:8]

        if writer is not None:
            # 发送执行开始标记
            try:
                writer({
                    "tool": "execute_script",
                    "stage": "running",
                    "execution_id": execution_id,
                    "name": params.name,
                    "message": f"开始执行脚本 '{params.name}'",
                })
            except Exception:
                pass

            # 流式执行：逐行推送输出
            def _on_output(line: str, stream: str) -> None:
                try:
                    writer({
                        "tool": "execute_script",
                        "stage": "output",
                        "execution_id": execution_id,
                        "stream": stream,
                        "message": line,
                    })
                except Exception:
                    pass

            result = executor.execute_python_script_stream(
                script_name=params.name,
                args=params.args,
                output_callback=_on_output,
                execution_id=execution_id,
            )
        else:
            # 非流式执行（兼容无 runtime 环境）
            result = executor.execute_python_script(
                script_name=params.name,
                args=params.args,
            )

        response = {
            "ok": result["ok"],
            "action": "execute",
            "name": params.name,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "returncode": result["returncode"],
        }

        # 发送执行完成标记
        if writer is not None:
            try:
                writer({
                    "tool": "execute_script",
                    "stage": "completed",
                    "execution_id": execution_id,
                    "name": params.name,
                    "returncode": result["returncode"],
                    "ok": result["ok"],
                    "message": f"脚本 '{params.name}' 执行完成，退出码 {result['returncode']}",
                })
            except Exception:
                pass

        return json.dumps(response, ensure_ascii=False)

    except ValueError as e:
        return _error_response("execute", str(e))


# ====================================================================
# 文件系统查看（ls / cat）
# ====================================================================


@tool
def list_sandbox_directory(params: ListDirectoryParams) -> str:
    """列出沙箱工作目录下指定文件夹的内容（类似 ls 命令）。

    返回目录中的子目录和文件列表，包含名称、类型、大小（文件）和最后修改时间。
    只能访问沙箱工作目录范围内的路径。

    Args:
        params: 包含 path（相对路径，如 "." 表示沙箱根目录，"subfolder" 表示子目录）。

    Returns:
        JSON: { "ok": true, "action": "list_directory", "path": "...", "entries": [...], "summary": "..." }。
    """
    try:
        sandbox_dir = get_sandbox_dir()
        target_path = validate_path(params.path, sandbox_dir)

        p = Path(target_path)
        if not p.exists():
            return _error_response("list_directory", f"路径不存在: {params.path}")
        if not p.is_dir():
            return _error_response("list_directory", f"路径不是目录: {params.path}")

        entries = []
        for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            stat = child.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
            entry = {
                "name": child.name,
                "type": "directory" if child.is_dir() else "file",
                "size": stat.st_size if child.is_file() else None,
                "modified_at": mtime,
            }
            entries.append(entry)

        summary = f"{len(entries)} 个条目"
        return _ok_response(
            "list_directory",
            path=str(p.relative_to(sandbox_dir) if p != sandbox_dir else "."),
            entries=entries,
            summary=summary,
        )
    except PermissionError as e:
        return _error_response("list_directory", str(e))
    except ValueError as e:
        return _error_response("list_directory", str(e))


@tool
def read_sandbox_file(params: ReadFileParams) -> str:
    """读取沙箱工作目录中指定文件的内容（类似 cat 命令）。

    文本文件直接返回内容；二进制文件不支持读取。
    大文件内容会被截断（上限 10KB），通过 truncated 字段指示。
    只能访问沙箱工作目录范围内的文件。

    Args:
        params: 包含 path（相对于沙箱目录的文件路径）。

    Returns:
        JSON: { "ok": true, "action": "read_file", "path": "...", "content": "...", "size": ..., "truncated": false }。
    """
    try:
        sandbox_dir = get_sandbox_dir()
        target_path = validate_path(params.path, sandbox_dir)

        p = Path(target_path)
        if not p.exists():
            return _error_response("read_file", f"文件不存在: {params.path}")
        if not p.is_file():
            return _error_response("read_file", f"路径不是文件: {params.path}")

        # 尝试以文本模式读取
        try:
            content = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, LookupError):
            return _error_response("read_file", f"无法以文本方式读取文件（可能是二进制文件）: {params.path}")

        file_size = p.stat().st_size
        max_chars = 10000
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... (已截断，文件共 {file_size} 字节，仅显示前 {max_chars} 字符)"
            truncated = True

        rel_path = str(p.relative_to(sandbox_dir))
        return _ok_response(
            "read_file",
            path=rel_path,
            content=content,
            size=file_size,
            truncated=truncated,
        )
    except PermissionError as e:
        return _error_response("read_file", str(e))
    except ValueError as e:
        return _error_response("read_file", str(e))
    except Exception as e:
        return _error_response("execute", f"执行异常: {e}")
