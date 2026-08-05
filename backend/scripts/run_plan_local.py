import sys, os, traceback
script_dir = os.path.dirname(__file__)
repo_root = os.path.dirname(script_dir)
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, 'backend'))

from src.services.course_recommendation import (
    fetch_term_schedule,
    fetch_completed_courses,
    fetch_course_offerings,
    build_student_profile,
    plan_schedule,
)

term_id = '2026-1'
try:
    schedule = fetch_term_schedule(term_id)
    print('Fetched schedule: term=', schedule.term)
    completed = fetch_completed_courses()
    print('Completed courses:', len(completed))
    offerings = fetch_course_offerings(term_id)
    print('Offerings count:', len(offerings))
    profile = build_student_profile(completed, major='Computer Science', interests=['ml'], career_goal='research', recommendation_note='偏好下午课')
    print('Profile built')
    plan = plan_schedule(schedule.term, profile, offerings, schedule.meetings, max_credits=18, use_llm=False)
    print('Plan generated:', plan)
except Exception as e:
    print('EXCEPTION:', e)
    traceback.print_exc()
    raise
