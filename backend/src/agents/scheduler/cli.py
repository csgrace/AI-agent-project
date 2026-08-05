"""CLI entrypoint for the scheduler agent (可被统一 CLI 启动器调用)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from ...core.global_state import get_calendar, get_draft_calendar
from ...models.calendar.enums import DirtyType
from ...services.init_calendar.loader import save_calendar_to_file
from ...services.llm_config import LLMConfig
from ...tools.operator_calendar.utils import reset_draft_from_main
from .agent import SchedulerDemoAgent, initialize_demo_state


CLI_CALENDAR_PATH = Path(__file__).resolve().parents[3] / "resources" / "calendar.json"


def _build_chat_model() -> ChatOpenAI:
    llm = LLMConfig.get_instance().build_chat_model(tier="smart")
    if llm is None:
        raise RuntimeError(
            "No model credentials found. "
            "Please set DASHSCOPE_API_KEY or OPENAI_API_KEY in .env, "
            "or provide an API key via the web UI."
        )
    return llm


def _confirm_commit_and_save(calendar_persist_path: Path) -> int:
    """Commit current draft into main calendar and persist to disk."""
    calendar = get_calendar()
    draft = get_draft_calendar()
    if calendar is None:
        raise ValueError("Calendar is not initialized")
    if draft is None:
        raise ValueError("Draft calendar is not initialized")

    synced_count = calendar.sync_draft(draft, partial_update=False)
    draft.dirty = DirtyType.CLEAR
    save_calendar_to_file(calendar, calendar_persist_path)
    return synced_count


def _save_main_calendar(calendar_persist_path: Path) -> Path | None:
    """Persist main calendar when available."""
    calendar = get_calendar()
    if calendar is None:
        return None
    return save_calendar_to_file(calendar, calendar_persist_path)


def run_scheduler_cli(*, calendar_path: Path | None = None) -> None:
    """Run interactive CLI for the scheduler demo.

    This function is called by the unified CLI launcher (``agents/cli.py``).
    It assumes ``initialize_demo_state()`` has already been called by the
    launcher, so it does **not** call it again — it reuses the existing
    global calendar/draft state.
    """
    load_dotenv()

    llm = _build_chat_model()
    summary_trigger = int(os.getenv("AGENT_SUMMARY_TRIGGER", "36"))
    summary_keep = int(os.getenv("AGENT_SUMMARY_KEEP", "14"))
    agent = SchedulerDemoAgent(
        llm,
        max_steps=10,
        summary_trigger=summary_trigger,
        summary_keep=summary_keep,
    )
    debug_stream = os.getenv("AGENT_DEBUG_STREAM", "1") == "1"
    debug_payload = os.getenv("AGENT_DEBUG_TOOL_PAYLOAD", "0") == "1"
    persist_path = calendar_path or CLI_CALENDAR_PATH

    print("Scheduler Agent started. Input your request. Type /exit to return to menu. Use /draft to inspect draft calendar.")

    try:
        while True:
            user_text = input("\nYou> ").strip()
            if not user_text:
                continue
            if user_text.lower() in {"/exit", "exit", "quit"}:
                print("Returning to menu.")
                return
            if user_text.lower() == "/draft":
                draft_calendar = get_draft_calendar()
                if draft_calendar is None:
                    print("\nDraft> Draft calendar is not initialized.")
                else:
                    print("\nDraft>")
                    print(draft_calendar.model_dump_json(indent=2))
                continue

            result = None
            for event in agent.run_turn_stream(user_text):
                if event["event"] == "thought" and debug_stream:
                    print(f"[Thought] {event['text']}")
                elif event["event"] == "tool_call" and debug_stream:
                    if debug_payload:
                        print(f"[Tool] calling {event['tool_name']} args={event['tool_args']}")
                    else:
                        print(f"[Tool] calling {event['tool_name']}")
                elif event["event"] == "tool_result" and debug_stream:
                    output = event.get("tool_output", "")
                    if not debug_payload and len(output) > 200:
                        output = output[:200] + "..."
                    print(f"[Tool] result {output}")
                elif event["event"] == "tool_progress" and debug_stream:
                    stage = event.get("stage", "")
                    message = event.get("message", "")
                    if stage:
                        print(f"[Progress] {stage}: {message}")
                    else:
                        print(f"[Progress] {message}")
                elif event["event"] == "error":
                    print(f"[Error] {event['message']}")
                elif event["event"] == "final":
                    result = event

            if result is None:
                result = {"reply": "", "finished": False, "requires_commit": False}

            print(f"\nAgent> {result['reply']}")

            draft_calendar = get_draft_calendar()
            requires_commit = bool(
                draft_calendar is not None and draft_calendar.dirty != DirtyType.CLEAR
            )
            if requires_commit:
                commit = input("\nCommit draft to calendar? (y/N): ").strip().lower()
                if commit in {"y", "yes"}:
                    synced_count = _confirm_commit_and_save(persist_path)
                    print(f"Committed {synced_count} events to main calendar.")
                else:
                    reset_count = reset_draft_from_main()
                    print(f"Draft reset from main calendar ({reset_count} events).")
                print("You can continue chatting, or type /exit to return to menu.")
    finally:
        _save_main_calendar(persist_path)


if __name__ == "__main__":
    load_dotenv()
    initialize_demo_state(calendar_path=CLI_CALENDAR_PATH)
    run_scheduler_cli()
