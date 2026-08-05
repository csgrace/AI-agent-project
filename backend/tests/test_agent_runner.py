"""Tests for create_agent runner wrapper."""

from langchain_core.messages import AIMessage

from src.agents.agent_runner import AgentRunner


class FakeCompiledAgent:
    """Minimal compiled agent stub for runner tests."""

    def __init__(self, ai_content: str) -> None:
        self.ai_content = ai_content

    def invoke(self, payload, config=None):
        messages = list(payload["messages"])
        messages.append(AIMessage(content=self.ai_content))
        return {"messages": messages}


class FakeStreamCompiledAgent:
    """Compiled agent stub that emits custom and values stream chunks."""

    def stream(self, payload, config=None, stream_mode=None):
        messages = list(payload["messages"])
        yield (
            "custom",
            {
                "tool": "convert_html_calendar_to_events",
                "stage": "ocr",
                "message": "Running OCR",
            },
        )
        yield ("values", {"messages": [*messages, AIMessage(content="FINISH: streamed")]})


class FakeCompiledAgentWithCommit:
    """Invoke path agent stub that returns requires_commit state."""

    def invoke(self, payload, config=None):
        messages = list(payload["messages"])
        messages.append(AIMessage(content="all set"))
        return {"messages": messages, "requires_commit": True}


class FakeStreamCompiledAgentWithCommit:
    """Stream path agent stub that emits requires_commit in state payload."""

    def stream(self, payload, config=None, stream_mode=None):
        messages = list(payload["messages"])
        yield (
            "values",
            {
                "messages": [*messages, AIMessage(content="not finished")],
                "requires_commit": True,
            },
        )


def test_runner_returns_finish_payload():
    runner = AgentRunner(FakeCompiledAgent("FINISH: completed"), max_steps=4)

    result = runner.run_turn("hello")

    assert result["finished"] is True
    assert result["reply"].startswith("FINISH:")
    assert result["steps"] >= 1


def test_runner_preserves_message_history():
    runner = AgentRunner(FakeCompiledAgent("keep going"), max_steps=4)

    runner.run_turn("first")
    runner.run_turn("second")

    # Two user turns + two AI replies
    assert len(runner.messages) == 4


def test_runner_stream_emits_thought_and_final_events():
    runner = AgentRunner(FakeCompiledAgent("FINISH: streamed"), max_steps=4)

    events = list(runner.run_turn_stream("hello"))

    assert events[0]["event"] == "thought"
    assert events[0]["text"].startswith("FINISH:")
    assert events[-1]["event"] == "final"
    assert events[-1]["finished"] is True


def test_runner_run_turn_matches_stream_final():
    runner = AgentRunner(FakeCompiledAgent("FINISH: from run_turn"), max_steps=4)

    result = runner.run_turn("hi")

    assert result["finished"] is True
    assert result["reply"].startswith("FINISH:")


def test_runner_stream_emits_custom_progress_events():
    runner = AgentRunner(FakeStreamCompiledAgent(), max_steps=4)

    events = list(runner.run_turn_stream("hello"))

    assert any(event["event"] == "tool_progress" for event in events)
    progress = next(event for event in events if event["event"] == "tool_progress")
    assert progress["stage"] == "ocr"
    assert events[-1]["event"] == "final"


def test_runner_run_turn_includes_requires_commit_from_invoke_state():
    runner = AgentRunner(FakeCompiledAgentWithCommit(), max_steps=4)

    result = runner.run_turn("save draft")

    assert result["requires_commit"] is True


def test_runner_stream_final_includes_requires_commit_from_state_payload():
    runner = AgentRunner(FakeStreamCompiledAgentWithCommit(), max_steps=4)

    events = list(runner.run_turn_stream("save draft"))

    assert events[-1]["event"] == "final"
    assert events[-1]["requires_commit"] is True
