"""Default tool set for the script automation agent."""

from __future__ import annotations

from typing import Any, List

from ...tools.script_automation.tool import (
    create_script,
    read_script,
    update_script,
    delete_script,
    list_scripts,
    list_sandbox_directory,
    read_sandbox_file,
    install_sandbox_package,
    list_sandbox_packages,
    execute_script,
)
from ...tools.skill_loader.tool import load_skill


def default_script_tools() -> List[Any]:
    """Return the default tool set for the script automation agent."""
    return [
        # ── 脚本管理 ────────────────────────────────────
        create_script,
        read_script,
        update_script,
        delete_script,
        list_scripts,
        # ── 文件系统查看 ────────────────────────────────
        list_sandbox_directory,
        read_sandbox_file,
        # ── 包管理 ──────────────────────────────────────
        install_sandbox_package,
        list_sandbox_packages,
        # ── 脚本执行 ────────────────────────────────────
        execute_script,
        # ── 技能加载（可选） ────────────────────────────
        load_skill,
    ]
