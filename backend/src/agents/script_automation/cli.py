"""CLI entrypoint for the script automation agent (可被统一 CLI 启动器调用)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from ...services.llm_config import LLMConfig
from .agent import ScriptAutomationAgent


def _build_chat_model() -> ChatOpenAI:
    llm = LLMConfig.get_instance().build_chat_model(tier="smart")
    if llm is None:
        raise RuntimeError(
            "No model credentials found. "
            "Please set DASHSCOPE_API_KEY or OPENAI_API_KEY in .env, "
            "or provide an API key via the web UI."
        )
    return llm


def run_script_cli(*, sandbox_dir: Path | None = None) -> None:
    """Run interactive CLI for the script automation agent.

    This function is called by the unified CLI launcher (``agents/cli.py``).
    It assumes ``initialize_script_state()`` has already been called by the
    launcher, so it does **not** call it again — it reuses the existing
    global sandbox state.
    """
    load_dotenv()

    llm = _build_chat_model()
    summary_trigger = int(os.getenv("AGENT_SUMMARY_TRIGGER", "36"))
    summary_keep = int(os.getenv("AGENT_SUMMARY_KEEP", "14"))
    agent = ScriptAutomationAgent(
        llm,
        max_steps=10,
        summary_trigger=summary_trigger,
        summary_keep=summary_keep,
    )
    debug_stream = os.getenv("AGENT_DEBUG_STREAM", "1") == "1"
    debug_payload = os.getenv("AGENT_DEBUG_TOOL_PAYLOAD", "0") == "1"

    print("Script Automation Agent started. I can help you create, manage, and execute Python automation scripts.")
    print("Commands: /exit return to menu | /scripts list all scripts | /sandbox show sandbox info")

    try:
        while True:
            user_text = input("\nYou> ").strip()
            if not user_text:
                continue
            if user_text.lower() in {"/exit", "exit", "quit"}:
                print("Returning to menu.")
                return
            if user_text.lower() == "/scripts":
                # Quick list via tool call
                from ...tools.script_automation.tool import list_scripts
                from ...tools.script_automation.schemas import ListScriptsParams

                result = list_scripts(ListScriptsParams())
                print(f"\nScripts> {result}")
                continue
            if user_text.lower() == "/sandbox":
                from ...core.global_state import get_script_sandbox_dir

                sandbox = get_script_sandbox_dir()
                if sandbox:
                    print(f"\nSandbox> {sandbox}")
                else:
                    print("\nSandbox> Not initialized.")
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
                result = {"reply": "", "finished": False}

            print(f"\nAgent> {result['reply']}")
    except KeyboardInterrupt:
        print("\nReturning to menu.")


if __name__ == "__main__":
    load_dotenv()
    from .agent import initialize_script_state
    initialize_script_state()
    run_script_cli()
