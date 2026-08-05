#!/usr/bin/env python3
"""Unified CLI launcher for Smart Campus Assistant.

Usage::

    python -m backend.src.agents.cli

Select an agent from the menu to start an interactive session.
Global state (calendar, skills, object store) is initialised once
at startup and shared across all agent sessions within the same
process lifetime.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from ..core.global_state import get_calendar
from ..services.init_calendar.loader import save_calendar_to_file
from .scheduler.agent import initialize_demo_state
from .script_automation.agent import initialize_script_state


CLI_CALENDAR_PATH = Path(__file__).resolve().parents[2] / "resources" / "calendar.json"


def _clear_screen() -> None:
    """Clear terminal screen (cross-platform)."""
    os.system("cls" if os.name == "nt" else "clear")


def _print_banner() -> None:
    _clear_screen()
    print("=" * 56)
    print("     Smart Campus Assistant — Unified CLI")
    print("=" * 56)
    print()


def _show_menu() -> str:
    print("\nAvailable agents:")
    print("  [1]  Scheduler Agent   — 日程规划与任务管理")
    print("  [2]  Script Agent      — 创建与管理自动化脚本")
    print()
    print("  [0]  Exit")
    print()
    return input("Select > ").strip()


def _run_scheduler() -> None:
    """Launch the scheduler agent CLI, then return to menu."""
    from .scheduler.cli import run_scheduler_cli

    _clear_screen()
    print("── Scheduler Agent ──────────────────────────────")
    run_scheduler_cli(calendar_path=CLI_CALENDAR_PATH)


def _run_script() -> None:
    """Launch the script automation agent CLI, then return to menu."""
    from .script_automation.cli import run_script_cli

    _clear_screen()
    print("── Script Automation Agent ──────────────────────")
    run_script_cli()


def main() -> None:
    load_dotenv()

    # ── Initialise global state once ──────────────────────
    initialize_demo_state(calendar_path=CLI_CALENDAR_PATH)
    initialize_script_state()

    # ── Menu loop ─────────────────────────────────────────
    _print_banner()

    while True:
        choice = _show_menu()

        if choice == "1":
            _run_scheduler()
            _print_banner()
        elif choice == "2":
            _run_script()
            _print_banner()
        elif choice == "0":
            print("Bye.")
            return
        else:
            print(f"  Unknown option: {choice!r}. Please try again.")

    # ── Persist on exit ───────────────────────────────────
    # (the scheduler CLI also saves on /exit, but this is a
    #  safety net in case of unexpected exit from the menu.)


def _save_on_exit() -> None:
    calendar = get_calendar()
    if calendar is not None:
        try:
            save_calendar_to_file(calendar, CLI_CALENDAR_PATH)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    finally:
        _save_on_exit()
