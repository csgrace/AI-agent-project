"""Tests for create_agent-based scheduler demo agent."""

from pathlib import Path

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.agents.scheduler.agent import SchedulerDemoAgent, initialize_demo_state
from src.agents.scheduler.tools import default_demo_tools
from src.core.global_state import get_draft_calendar, get_skill_registry
from src.models.calendar.enums import DirtyType


class BindableFakeListChatModel(FakeListChatModel):
    """Fake model that exposes bind_tools for create_agent compatibility."""

    def bind_tools(self, tools, **kwargs):  # pragma: no cover - trivial adapter
        return self


def test_run_turn_finishes_with_fake_model():
    model = BindableFakeListChatModel(responses=["FINISH: done"])
    agent = SchedulerDemoAgent(model, tools=[], max_steps=4)

    result = agent.run_turn("start")

    assert result["finished"] is True
    assert result["reply"].startswith("FINISH:")
    assert len(agent.messages) >= 2


def test_run_turn_stream_emits_final_event():
    model = BindableFakeListChatModel(responses=["FINISH: stream done"])
    agent = SchedulerDemoAgent(model, tools=[], max_steps=4)

    events = list(agent.run_turn_stream("start"))

    assert events[-1]["event"] == "final"
    assert events[-1]["finished"] is True


def test_initialize_demo_state_registers_skills(tmp_path: Path):
    persist_path = tmp_path / "calendar.json"
    skills_dir = tmp_path / "skills"
    skill_folder = skills_dir / "demo_skill"
    skill_folder.mkdir(parents=True)
    (skill_folder / "skill.md").write_text(
        "---\n"
        "name: demo_skill\n"
        "description: demo description\n"
        "---\n\n"
        "# demo_skill\n",
        encoding="utf-8",
    )

    initialize_demo_state(calendar_path=persist_path, skills_dir=skills_dir)
    registry = get_skill_registry()

    assert "demo_skill" in registry
    assert registry["demo_skill"]["description"] == "demo description"


def test_default_demo_tools_include_load_skill():
    tool_names = {tool.name for tool in default_demo_tools()}

    assert "load_skill" in tool_names
    assert "reset_draft" in tool_names


def test_initialize_demo_state_marks_draft_clean(tmp_path: Path):
    persist_path = tmp_path / "calendar.json"

    initialize_demo_state(calendar_path=persist_path)
    draft = get_draft_calendar()

    assert draft is not None
    assert draft.dirty == DirtyType.CLEAR
