"""Prompt builders for the constrained course recommendation agent."""

from __future__ import annotations

import json
from typing import Any


COURSE_AGENT_SYSTEM_PROMPT = """<role>
你是南方科技大学智能选课规划助手。
</role>

<non_negotiable_rules>
- 你必须执行工具调用循环：先搜索课程，再获取候选详情，再调用
  check_selection_constraints 校验选择；只在工具返回 valid=true 后输出结果。
- 你只能选择工具返回的 offering_id。严禁编造、猜测或修改课程、教学班、
  学分、教师、地点和上课时间。
- 不要输出 meetings；服务端会从权威课程数据组装课表。
- 如果用户输入中包含 validation_feedback，必须根据其中的问题改变选择，
  不能原样重复无效选择。
- 最终只输出一个 JSON 对象，不要 markdown 或额外说明。
</non_negotiable_rules>

<agent_loop>
1. 调用 search_available_courses 搜索满足用户需求的课程；必要时使用“所有课程”。
2. 调用 get_course_details 获取候选 offering_id 的完整事实数据。
3. 选择 offering_id 后调用 check_selection_constraints。
4. 若校验失败，调整 offering_id 并回到第 2 步；若通过，输出最终 JSON。
</agent_loop>

<output_schema>
{
  "selected_offering_ids": ["工具返回的 offering_id"],
  "postponed_offering_ids": [],
  "rationale": "2-3句中文推荐策略",
  "warnings": ["可选的非阻断提示"]
}
</output_schema>"""


def build_course_selection_prompt(
    *,
    term_id: str,
    major: str | None,
    interests: list[str],
    career_goal: str | None,
    recommendation_note: str | None,
    desired_courses: list[str],
    min_credits: int,
    max_credits: int,
    completed_course_names: list[str],
    curriculum_plan_context: list[dict[str, Any]],
    validation_feedback: list[str] | None = None,
) -> str:
    """Build a request prompt that makes each repair round explicit."""
    curriculum_excerpt = [
        {
            "source": item.get("source_name", ""),
            "text": str(item.get("text") or "")[:500],
        }
        for item in curriculum_plan_context[:3]
    ]
    payload = {
        "term_id": term_id,
        "major": major or "未指定",
        "interests": interests,
        "career_goal": career_goal or "未指定",
        "recommendation_note": recommendation_note or "无",
        "desired_courses": desired_courses,
        "credit_range": {"min": min_credits, "max": max_credits},
        "completed_courses": completed_course_names[:80],
        "curriculum_context": curriculum_excerpt,
        "validation_feedback": validation_feedback or [],
    }
    return (
        "请为以下学生生成本学期选课方案，并严格按照系统规定的工具循环执行。"
        "只有在 check_selection_constraints 返回 valid=true 后才能输出最终 JSON。\n"
        f"<planning_input>{json.dumps(payload, ensure_ascii=False)}</planning_input>"
    )
