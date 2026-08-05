"""Script file storage manager — CRUD operations on .scripts/ in the sandbox dir.

所有操作基于当前沙箱工作目录（global_state.SCRIPT_SANDBOX_DIR），
脚本文件存储在 {sandbox_dir}/.scripts/{name}.py，
元数据存储在 {sandbox_dir}/.scripts/metadata.json。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .safety import get_sandbox_dir


def _get_scripts_dir() -> Path:
    """获取当前沙箱的 .scripts/ 目录路径，如果不存在则创建。"""
    sandbox_dir = get_sandbox_dir()
    scripts_dir = sandbox_dir / ".scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    # 创建 .gitkeep 确保目录被版本控制跟踪（如果沙箱在项目内）
    gitkeep = scripts_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()
    return scripts_dir


def _load_metadata() -> Dict[str, Any]:
    """从 {sandbox_dir}/.scripts/metadata.json 加载元数据。"""
    meta_path = _get_scripts_dir() / "metadata.json"
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_metadata(metadata: Dict[str, Any]) -> None:
    """将元数据写入 {sandbox_dir}/.scripts/metadata.json。"""
    meta_path = _get_scripts_dir() / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def create_script_file(
    name: str,
    content: str,
    description: str = "",
    category: str = "general",
) -> str:
    """创建一个新的自动化脚本文件。

    Args:
        name: 脚本名称（不含 .py 后缀）。
        content: 脚本 Python 代码。
        description: 功能描述。
        category: 分类标签。

    Returns:
        成功消息。

    Raises:
        ValueError: 如果脚本已存在或名称不合法。
    """
    scripts_dir = _get_scripts_dir()

    # 验证名称合法性
    if not name or "/" in name or "\\" in name:
        raise ValueError(f"脚本名称不合法: '{name}'")

    script_path = scripts_dir / f"{name}.py"
    if script_path.exists():
        raise ValueError(f"脚本 '{name}' 已存在。如需修改请使用 update_script。")

    # 写入脚本文件
    script_path.write_text(content, encoding="utf-8")

    # 更新元数据
    metadata = _load_metadata()
    metadata[name] = {
        "name": name,
        "description": description,
        "category": category,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_metadata(metadata)

    return f"脚本 '{name}' 创建成功 ({script_path})"


def read_script_file(name: str) -> Tuple[str, Dict[str, Any]]:
    """读取指定脚本的内容和元数据。

    Args:
        name: 脚本名称。

    Returns:
        (content, metadata) 元组。

    Raises:
        ValueError: 如果脚本不存在。
    """
    scripts_dir = _get_scripts_dir()
    script_path = scripts_dir / f"{name}.py"

    if not script_path.exists():
        raise ValueError(f"脚本 '{name}' 不存在。可用 list_scripts 查看所有脚本。")

    content = script_path.read_text(encoding="utf-8")
    metadata = _load_metadata().get(name, {})

    return content, metadata


def update_script_file(
    name: str,
    content: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    """更新指定脚本的内容或元信息。

    Args:
        name: 脚本名称。
        content: 新的代码（可选）。
        description: 新的描述（可选）。
        category: 新的分类（可选）。

    Returns:
        成功消息。

    Raises:
        ValueError: 如果脚本不存在。
    """
    scripts_dir = _get_scripts_dir()
    script_path = scripts_dir / f"{name}.py"

    if not script_path.exists():
        raise ValueError(f"脚本 '{name}' 不存在。")

    # 更新内容
    if content is not None:
        script_path.write_text(content, encoding="utf-8")

    # 更新元数据
    metadata = _load_metadata()
    if name in metadata:
        if description is not None:
            metadata[name]["description"] = description
        if category is not None:
            metadata[name]["category"] = category
        metadata[name]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _save_metadata(metadata)

    changed = []
    if content is not None:
        changed.append("内容")
    if description is not None:
        changed.append("描述")
    if category is not None:
        changed.append("分类")

    return f"脚本 '{name}' 更新成功 ({', '.join(changed)})"


def delete_script_file(name: str) -> str:
    """删除指定脚本。

    Args:
        name: 脚本名称。

    Returns:
        成功消息。

    Raises:
        ValueError: 如果脚本不存在。
    """
    scripts_dir = _get_scripts_dir()
    script_path = scripts_dir / f"{name}.py"

    if not script_path.exists():
        raise ValueError(f"脚本 '{name}' 不存在。")

    script_path.unlink()

    metadata = _load_metadata()
    metadata.pop(name, None)
    _save_metadata(metadata)

    return f"脚本 '{name}' 已删除"


def list_script_files() -> str:
    """列出当前沙箱中的所有脚本。

    Returns:
        格式化的脚本列表。
    """
    scripts_dir = _get_scripts_dir()
    metadata = _load_metadata()

    # 扫描 .scripts/ 下的 .py 文件
    script_names = set()
    for f in scripts_dir.iterdir():
        if f.suffix == ".py" and f.name != "__init__.py":
            script_names.add(f.stem)

    if not script_names:
        return "当前沙箱中没有自动化脚本。可用 create_script 创建。"

    lines = [f"当前沙箱中的脚本 ({scripts_dir}):\n"]
    for name in sorted(script_names):
        meta = metadata.get(name, {})
        desc = meta.get("description", "")
        cat = meta.get("category", "general")
        updated = meta.get("updated_at", "")
        desc_part = f" — {desc}" if desc else ""
        lines.append(f"  📄 {name}.py  [{cat}]{desc_part}")
        if updated:
            lines.append(f"     上次更新: {updated}")

    # 统计目录中所有脚本的总行数
    total_lines = 0
    for name in script_names:
        fp = scripts_dir / f"{name}.py"
        if fp.exists():
            total_lines += len(fp.read_text(encoding="utf-8").splitlines())

    lines.append(f"\n共 {len(script_names)} 个脚本，{total_lines} 行代码")
    return "\n".join(lines)


def get_script_path(name: str) -> Path:
    """获取指定脚本的完整路径。

    Args:
        name: 脚本名称。

    Returns:
        脚本文件的 Path 对象。

    Raises:
        ValueError: 如果脚本不存在。
    """
    scripts_dir = _get_scripts_dir()
    script_path = scripts_dir / f"{name}.py"
    if not script_path.exists():
        raise ValueError(f"脚本 '{name}' 不存在。")
    return script_path
