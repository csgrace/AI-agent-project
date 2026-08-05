"""Tests for agent_factory runtime prompt behavior."""

from src.agents.agent_factory import build_runtime_system_prompt


def test_runtime_prompt_uses_cn_naive_time_policy():
    prompt = build_runtime_system_prompt("base")

    assert "Asia/Shanghai, naive" in prompt
    assert "without timezone offsets" in prompt
    assert "Current runtime datetime" in prompt
