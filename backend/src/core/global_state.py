"""Global state module for sharing variables across the application."""
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..models.calendar.calendar import Calendar
from ..models.calendar.draft_calendar import DraftCalendar
from .object_store import ObjectStore

# 沙箱目录持久化配置文件名（存储在 backend/resources/ 下）
SANDBOX_CONFIG_FILENAME = "sandbox_config.json"

SKILL_REGISTRY: Dict[str, Dict[str, Any]] = {}

CALENDAR: Optional[Calendar] = None

DRAFT_CALENDAR: Optional[DraftCalendar] = None

OBJECT_STORE: ObjectStore = ObjectStore()

# 自动化脚本沙箱工作目录（指向一个包含 .scripts/ + .venv/ 的自包含目录）
SCRIPT_SANDBOX_DIR: Optional[str] = None


def get_skill_registry() -> Dict[str, Dict[str, Any]]:
    """Get the global skill registry.

    Returns:
        Dict mapping skill names to their metadata.
    """
    return SKILL_REGISTRY


def get_calendar() -> Optional[Calendar]:
    """Get the global calendar instance.

    Returns:
        The global Calendar instance, or None if not initialized.
    """
    return CALENDAR


def set_calendar(calendar: Calendar) -> None:
    """Set the global calendar instance.

    Args:
        calendar: The Calendar instance to set as global.
    """
    global CALENDAR
    CALENDAR = calendar


def get_draft_calendar() -> Optional[DraftCalendar]:
    """Get the global draft calendar instance.

    Returns:
        The global DraftCalendar instance, or None if not initialized.
    """
    return DRAFT_CALENDAR


def set_draft_calendar(draft_calendar: DraftCalendar) -> None:
    """Set the global draft calendar instance.

    Args:
        draft_calendar: The DraftCalendar instance to set as global.
    """
    global DRAFT_CALENDAR
    DRAFT_CALENDAR = draft_calendar


def get_object_store() -> ObjectStore:
    """Get the global ObjectStore instance."""
    return OBJECT_STORE


def set_object_store(object_store: ObjectStore) -> None:
    """Set the global ObjectStore instance.

    Args:
        object_store: The ObjectStore instance to set as global.
    """
    global OBJECT_STORE
    OBJECT_STORE = object_store


def get_script_sandbox_dir() -> Optional[str]:
    """Get the sandbox working directory for script automation.

    Returns:
        The absolute path to the sandbox directory, or None if not set.
    """
    return SCRIPT_SANDBOX_DIR


def set_script_sandbox_dir(path: str) -> None:
    """Set the sandbox working directory for script automation.

    This directory will contain .scripts/ (user scripts) and .venv/ (virtual env).
    All script automation tools operate within this directory.

    Args:
        path: Absolute path to the sandbox working directory.
    """
    global SCRIPT_SANDBOX_DIR
    SCRIPT_SANDBOX_DIR = path


def _get_sandbox_config_path() -> Path:
    """获取沙箱配置文件的完整路径。

    配置文件存放在 ``backend/resources/sandbox_config.json``。
    """
    # global_state.py 位于 backend/src/core/，向上 3 层到 backend/
    return Path(__file__).resolve().parents[2] / "resources" / SANDBOX_CONFIG_FILENAME


def save_script_sandbox_config(path: str) -> None:
    """将沙箱工作目录路径持久化到配置文件。

    Args:
        path: 沙箱目录的绝对路径。
    """
    config_path = _get_sandbox_config_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"sandbox_dir": path}, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[WARNING] Failed to save sandbox config: {e}")


def load_script_sandbox_config() -> Optional[str]:
    """从配置文件加载之前持久化的沙箱工作目录路径。

    Returns:
        之前保存的沙箱目录路径，如果不存在或读取失败则返回 None。
    """
    config_path = _get_sandbox_config_path()
    if not config_path.exists():
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sandbox_dir")
    except (json.JSONDecodeError, OSError):
        return None
