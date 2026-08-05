#!/usr/bin/env python3
"""
从学期课表 JSON 中提取已修课程，并从 all_courses_merged.json 中补充课程类别、学分。
匹配不到的课程，使用与智能问答助手完全相同的 RAG 流程（检索+LLM）获取信息。
输出文件：completed_courses_detailed.json
"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from ...rag_pipeline.llm_service import LLMService
from ...services.document_qa import get_document_qa_service


BACKEND_ROOT = Path(__file__).resolve().parents[3]

# 目录与文件路径
SCHEDULE_DIR = BACKEND_ROOT / "data" / "tis_download" / "course_schedule"
ALL_COURSES_JSON = BACKEND_ROOT / "data" / "tis_download" / "full_course_table" / "all_courses_merged.json"
OUTPUT_FILE = BACKEND_ROOT / "data" / "tis_download" / "completed_courses_detailed.json"

def extract_core_name(full_name: str) -> str:
    """提取核心课程名，去掉括号内容和班级/组/语言后缀"""
    if not full_name:
        return ""
    # 去掉括号及其内容
    name = re.sub(r'[（(][^）)]*[）)]', '', full_name)
    # 去掉类似 '-01班'、'-2组'、'-双语' 等后缀
    name = re.sub(r'[-_][0-9]+班.*$', '', name)
    name = re.sub(r'[-_][两三四五二一]组.*$', '', name)
    name = re.sub(r'[-_](?:双语|全英|英文)?$', '', name)
    name = name.strip()
    return name if name else full_name


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _course_aliases(full_name: str) -> list[str]:
    aliases: list[str] = []
    if not full_name:
        return aliases

    core = extract_core_name(full_name).strip()
    if core and core not in aliases:
        aliases.append(core)

    for chunk in re.split(r"[\s,，。；;、/|()（）]+", full_name):
        chunk = chunk.strip()
        if len(chunk) > 1 and chunk not in aliases:
            aliases.append(chunk)

    return aliases


def _best_course_match(query: str, candidates: list[str]) -> str:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return ""

    best_candidate = ""
    best_score = 0.0
    for candidate in candidates:
        normalized_candidate = _normalize_text(candidate)
        if not normalized_candidate:
            continue
        if normalized_query == normalized_candidate:
            return candidate
        if (
            normalized_query in normalized_candidate
            or normalized_candidate in normalized_query
        ):
            score = 0.95
        else:
            score = SequenceMatcher(
                None,
                normalized_query,
                normalized_candidate,
            ).ratio()
        if score > best_score:
            best_score = score
            best_candidate = candidate
    return best_candidate

def load_course_details() -> dict:
    """从 all_courses_merged.json 加载课程详细信息，建立 core_name -> (课程类别, 学分) 映射"""
    if not ALL_COURSES_JSON.exists():
        print(f"警告: 找不到 {ALL_COURSES_JSON}，将无法从本地匹配课程信息")
        return {}
    with open(ALL_COURSES_JSON, 'r', encoding='utf-8') as f:
        courses = json.load(f)
    mapping = {}
    for course in courses:
        if not isinstance(course, dict):
            continue
        full_name = course.get("课程名称", "")
        core = extract_core_name(full_name)
        detail = {
            "课程类别": course.get("课程类别", ""),
            "学分": course.get("学分", ""),
        }
        for alias in [full_name, core, *_course_aliases(full_name)]:
            normalized_alias = _normalize_text(alias)
            if normalized_alias and normalized_alias not in mapping:
                mapping[normalized_alias] = detail
    return mapping

def query_rag_for_general_info(course_name: str, core_name: str) -> dict:
    """
    使用与智能问答助手完全相同的 RAG 流程（检索 + LLM）获取课程的类别和学分。
    返回: {"课程类别": str, "学分": str}
    """
    try:
        qa_service = get_document_qa_service()
    except Exception as e:
        print(f"  无法加载问答服务: {e}")
        return {"课程类别": "", "学分": ""}
    
    query = f"{course_name} 课程类别 学分"
    results = qa_service.search(query, k=3)
    if not results:
        print(f"  未检索到相关文档 ({core_name})")
        return {"课程类别": "", "学分": ""}
    
    context = "\n\n".join([r.text for r in results])
    
    llm = LLMService()
    prompt = f"""基于以下参考资料，回答课程“{course_name}”的课程类别和学分。

参考资料：
{context}

请用中文回答，只输出一个 JSON 对象，格式为：{{"课程类别": "...", "学分": "..."}}，不要输出其他内容。"""
    
    try:
        response = llm._chat_completion(
            prompt,
            temperature=0,
            max_tokens=150,
            label=f"fetch_course_{core_name[:30]}",
            model=llm.lightweight_model_name,
            fallback_model=llm._lightweight_fallback_model,
        )
        print(f"  RAG 返回 ({core_name}): {response[:200] if response else 'None'}")
        # 提取 JSON
        json_match = re.search(r'\{[^{}]*\}', response or "")
        if json_match:
            data = json.loads(json_match.group(0))
            return {
                "课程类别": data.get("课程类别", ""),
                "学分": str(data.get("学分", "")) if data.get("学分") is not None else ""
            }
        else:
            # 降级：从自然语言中提取
            credits = re.search(r'(\d+(?:\.\d+)?)\s*学分', response or "")
            credit_str = credits.group(1) if credits else ""
            category = ""
            if "专业核心" in response:
                category = "专业核心课"
            elif "专业选修" in response:
                category = "专业选修课"
            elif "通识必修" in response:
                category = "通识必修课"
            elif "通识选修" in response:
                category = "通识选修课"
            elif "实践" in response:
                category = "实践课"
            return {"课程类别": category, "学分": credit_str}
    except Exception as e:
        print(f"  RAG 查询失败 ({core_name}): {e}")
        return {"课程类别": "", "学分": ""}


def query_rag_for_course_type(course_name: str, core_name: str, major: str) -> str:
    """
    查询课程在指定专业培养方案中的课程类型。
    返回: 课程类型字符串（如“专业基础课”“专业核心课”等）
    """
    if not major:
        return ""

    try:
        qa_service = get_document_qa_service()
    except Exception as e:
        print(f"  无法加载问答服务: {e}")
        return ""

    categories = [
        "思政类", "体育类", "军训类", "综合素质类", "美育类", "计算机类",
        "写作类", "外语类", "人文社科类", "数学类", "物理类", "化学类",
        "地生类", "专业导论类", "专业基础课", "专业核心课", "集中实践",
        "专业选修课", "国学类"
    ]
    categories_str = "、".join(categories)

    aliases = [course_name, core_name, *_course_aliases(course_name)]
    query = (
        f"在{major}专业的培养方案中，课程“{course_name}”属于以下哪一类："
        f"{categories_str}？只输出类别名称，不要输出其他内容。"
    )
    results = qa_service.search(query, k=5)
    if not results:
        print(f"  未检索到相关文档 ({core_name})")
        return ""

    context = "\n\n".join([r.text for r in results])
    llm = LLMService()
    prompt = f"""基于以下培养方案资料，回答问题。
问题：{query}
资料：{context}
只输出类别名称，不要输出其他内容。"""

    alias_hint = _best_course_match(course_name, aliases)
    if alias_hint and alias_hint != course_name:
        prompt += f"\n\n补充说明：该课程也可能以“{alias_hint}”或其别名出现。"

    try:
        response = llm._chat_completion(
            prompt,
            temperature=0,
            max_tokens=50,
            label=f"classify_{core_name[:30]}",
            model=llm.lightweight_model_name,
            fallback_model=llm._lightweight_fallback_model,
        )
        print(
            f"  RAG 分类查询返回 ({core_name}): {response[:100] if response else 'None'}"
        )
        for cat in categories:
            if cat in (response or ""):
                return cat
        return ""
    except Exception as e:
        print(f"  RAG 分类查询失败 ({core_name}): {e}")
        return ""

def extract_courses_from_json(json_path: Path, term_id: str):
    """从单个课表 JSON 文件中提取课程（仅课程名和学期）"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        meetings = data
    else:
        meetings = data.get("meetings", [])
    courses = []
    for meeting in meetings:
        course_name = meeting.get("course_name", "")
        if not course_name:
            continue
        courses.append({
            "course_name": course_name,
            "term_id": term_id
        })
    return courses


def build_completed_courses(force: bool = False, major: str = "") -> Path:
    """
    构建已修课程 JSON 文件。
    :param force: 如果为 True，强制重新生成；否则如果文件已存在且不为空，直接返回已有文件路径。
    :param major: 学生专业（如“计算机科学与技术”），用于查询课程在该专业中的类型。如果为空，则不查询课程类型。
    :return: 生成的 JSON 文件路径
    """
    if not force and OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0:
        print(f"已修课程文件已存在且有效: {OUTPUT_FILE}")
        return OUTPUT_FILE

    print("开始构建已修课程数据...")
    if not SCHEDULE_DIR.exists():
        raise FileNotFoundError(f"学期课表目录不存在: {SCHEDULE_DIR}")

    details_map = load_course_details()
    print(f"从 all_courses_merged.json 加载了 {len(details_map)} 门课程的详情映射")

    raw_courses = []
    for json_file in SCHEDULE_DIR.glob("*.json"):
        if json_file.name in ("completed_courses.json", "academic_progress.json", "completed_courses_detailed.json"):
            continue
        term_id = json_file.stem
        print(f"处理: {json_file.name} -> 学期: {term_id}")
        courses = extract_courses_from_json(json_file, term_id)
        raw_courses.extend(courses)
    print(f"共提取 {len(raw_courses)} 条课程记录")

    core_records = {}
    rag_cache = {}
    type_cache = {}

    for course in raw_courses:
        full_name = course["course_name"]
        core = extract_core_name(full_name)
        if core in core_records:
            continue

        details = details_map.get(_normalize_text(full_name)) or details_map.get(_normalize_text(core))
        if details:
            general_info = {
                "课程类别": details.get("课程类别", ""),
                "学分": details.get("学分", ""),
            }
        else:
            if core not in rag_cache:
                print(f"  本地未匹配课程: {core}，使用 RAG（与问答助手相同）查询...")
                rag_result = query_rag_for_general_info(full_name, core)
                rag_cache[core] = rag_result
            else:
                rag_result = rag_cache[core]
            general_info = {
                "课程类别": rag_result.get("课程类别", ""),
                "学分": rag_result.get("学分", ""),
            }

        course_type = ""
        if major:
            type_key = f"{core}|{major}"
            if type_key not in type_cache:
                print(f"  查询专业分类 ({major}): {core}")
                type_cache[type_key] = query_rag_for_course_type(full_name, core, major)
            course_type = type_cache[type_key]

        record = {
            "course_name": full_name,
            "term_id": course["term_id"],
            "课程类别": general_info.get("课程类别", ""),
            "学分": general_info.get("学分", ""),
            "课程类型": course_type,
            "status": "completed",
        }
        core_records[core] = record

    unique_courses = list(core_records.values())
    output = {
        "courses": unique_courses,
        "total_count": len(unique_courses)
    }
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"去重后共 {len(unique_courses)} 门课程")
    print(f"已生成: {OUTPUT_FILE}")
    return OUTPUT_FILE

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--major", type=str, default="", help="学生专业（例如：计算机科学与技术）")
    parser.add_argument("--force", action="store_true", help="强制重新生成")
    args = parser.parse_args()
    try:
        build_completed_courses(force=args.force, major=args.major)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()