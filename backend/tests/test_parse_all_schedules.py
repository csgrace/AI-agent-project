from pathlib import Path
import re as _re

# Extract the parse_all_schedules function source from the recommendation_engine
# file and exec it in this test module to avoid package import side-effects.
src_path = Path(__file__).resolve().parents[1] / 'src' / 'services' / 'course_recommendation' / 'recommendation_engine.py'
src_text = src_path.read_text(encoding='utf-8')
fn_match = _re.search(r"(def parse_all_schedules\(.*?\):\n(?:\s+.*\n)*)", src_text, _re.S)
assert fn_match, "could not extract parse_all_schedules"
fn_src = fn_match.group(1)
exec_globals = {"re": __import__('re'), "Any": __import__('typing').Any}
exec(fn_src, exec_globals)
parse_all_schedules = exec_globals['parse_all_schedules']


def test_parse_two_slots_semicolon():
    s = "1-16周,星期一第1-2节 一教101；星期三第3-4节 实验楼201"
    slots = parse_all_schedules(s)
    assert len(slots) == 2
    assert slots[0][0] == 1 and slots[1][0] == 3


def test_parse_two_slots_comma():
    s = "星期二第1-2节 一教101,星期四第5-6节 实验楼201"
    slots = parse_all_schedules(s)
    assert len(slots) == 2
    assert slots[0][0] == 2 and slots[1][0] == 4


def test_parse_slot_missing_location():
    s = "1-8周,星期五第1-2节；星期五第3-4节"
    slots = parse_all_schedules(s)
    assert len(slots) == 2
