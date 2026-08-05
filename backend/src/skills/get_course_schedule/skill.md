---
name: get_course_schedule
description: 获取学生课程表，自动从profile.json读取账号密码
---

# 获取课程表技能

## 技能描述

该技能用于通过CAS登录南科大TIS系统，获取学生的课程表信息。
自动从 profile.json 读取账号密码，并缓存 cookies 以便后续快速登录。

### 所用工具

- get_student_course_schedule: 获取课程表（自动处理登录，返回CalendarEvent对象列表）

## 技能步骤

1. 调用 `get_student_course_schedule` 工具获取课程表
2. 工具会自动：
   - 检查保存的 cookies 是否有效
   - 如果 cookies 无效，自动使用 profile.json 中的账号密码登录
   - 登录成功后自动保存新的 cookies
3. 将获取到的课程表信息整理后展示给用户

## 课程表信息格式

获取到的课程表事件为 CalendarEvent 对象，包含以下信息：

- **title**: 课程名称
- **description**: 课程描述（教师、班级信息）
- **scheduled_start**: 上课开始时间
- **deadline**: 上课结束时间
- **duration**: 课程持续时间（分钟）
- **location**: 上课地点
- **source**: 数据来源 (university)
- **category**: 事件类别 (background)

## 注意事项

- 课程表会转换为 CalendarEvent 格式，可以直接与系统其他日历事件集成
- cookies 有效期约为一学期，过期后会自动重新登录
- 首次使用需要确保 profile.json 中配置了正确的账号密码