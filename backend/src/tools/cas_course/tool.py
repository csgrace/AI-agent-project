from langchain.tools import ToolRuntime, tool
import sys
import os

# 添加src目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ...models.calendar.enums import DirtyType
from ...core.global_state import get_draft_calendar
from ...services.course_recommendation.tis_client import fetch_term_schedule

def _emit_progress(runtime: ToolRuntime, stage: str, message: str) -> None:
    writer = runtime.stream_writer
    if writer is None:
        return

    writer(
        {
            "tool": "fetch_student_course_schedule",
            "stage": stage,
            "message": message,
        }
    )

@tool
def fetch_student_course_schedule(runtime: ToolRuntime) -> str:
    """获取学生课程表并添加到草稿日历
    
    该工具通过CAS登录南科大TIS系统，获取学生的课程表信息，
    并将课程事件直接添加到草稿日历中。
    自动从profile.json读取账号密码，并缓存cookies以便后续使用。
    
    Returns:
        str: 成功消息，指示是否将事件添加到草稿日历。
    
    Raises:
        Exception: 当网络请求失败、解析错误或存在未提交的修改时
    
    Example:
        >>> result = fetch_student_course_schedule()
        >>> print(result)
        Successfully added events to draft calendar
    """
    # 检查是否有未提交的修改
    draft_calendar = get_draft_calendar()
    if draft_calendar is not None and draft_calendar.dirty == DirtyType.MODIFY:
        raise Exception("草稿日历中存在未提交的修改。请在获取新课程前提交或丢弃它们。")

    _emit_progress(runtime, "login", "正在登录南科大TIS系统...")
    
    try:
        _emit_progress(runtime, "fetch", "正在获取课程表数据...")
        schedule = fetch_term_schedule(
            "2025-2026-2",
            download_excel=True,
        )

        calendar_events = schedule.meetings
        
        # 将课程事件添加到草稿日历
        if draft_calendar is not None and calendar_events:
            _emit_progress(runtime, "update", f"正在将 {len(calendar_events)} 个课程事件添加到草稿日历...")
            draft_calendar.update_event_batch(calendar_events)
            draft_calendar.dirty = DirtyType.FETCH
            _emit_progress(runtime, "done", f"成功导入 {len(calendar_events)} 个课程事件到草稿日历")
            return "Successfully added events to draft calendar"
        else:
            _emit_progress(runtime, "done", "没有课程事件被导入到草稿日历")
            return "No events added to draft calendar"
    except Exception as e:
        _emit_progress(runtime, "error", f"获取课程表时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        raise