"""
合并所有课程表JSON文件
按"教学班"和"课程代码"联合去重，输出合并后的JSON和CSV文件
"""

import json
import csv
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime

# ==========================================================
# 路径配置
# ==========================================================
CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[3]  # 向上4级到 backend

DATA_DIR = BACKEND_ROOT / "data" / "tis_download" / "full_course_table"
JSON_DIR = DATA_DIR / "json"

# 输出文件路径
OUTPUT_JSON = DATA_DIR / "all_courses_merged.json"
OUTPUT_CSV = DATA_DIR / "all_courses_merged.csv"
DUPLICATE_REPORT = DATA_DIR / "duplicate_teaching_classes.txt"
MERGE_REPORT = DATA_DIR / "merge_report.txt"


class Tee:
    """同时将输出打印到终端和文件"""
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "w", encoding="utf-8")
        
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        
    def flush(self):
        self.terminal.flush()
        self.log.flush()
        
    def close(self):
        self.log.close()


def load_all_json_files() -> List[Dict[str, Any]]:
    """加载所有 page_*.json 文件"""
    all_courses = []
    json_files = sorted(JSON_DIR.glob("page_*.json"))
    
    print(f"找到 {len(json_files)} 个JSON文件")
    
    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                courses = json.load(f)
            
            if isinstance(courses, list):
                for course in courses:
                    if isinstance(course, dict):
                        # 添加来源文件信息（便于追踪）
                        course["_source_file"] = json_file.name
                        all_courses.append(course)
            else:
                print(f"  警告: {json_file.name} 不是数组格式，跳过")
        except Exception as e:
            print(f"  错误: 读取 {json_file.name} 失败: {e}")
    
    print(f"总共加载 {len(all_courses)} 条课程记录")
    return all_courses


def get_unique_key(course: Dict[str, Any]) -> str:
    """
    生成唯一键：教学班 + 课程代码
    如果两者都相同才算重复
    """
    teaching_class = course.get("教学班", "").strip()
    course_code = course.get("课程代码", "").strip()
    
    # 如果教学班为空，使用特殊标识
    if not teaching_class:
        teaching_class = "__EMPTY_CLASS__"
    
    # 如果课程代码为空，使用特殊标识
    if not course_code:
        course_code = "__EMPTY_CODE__"
    
    return f"{teaching_class}||{course_code}"


def deduplicate_by_class_and_code(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    按"教学班"和"课程代码"联合去重
    只有两者都相同时才视为重复
    """
    # 使用字典存储：key=教学班||课程代码, value=课程对象
    unique_courses: Dict[str, Dict[str, Any]] = {}
    # 记录重复信息：key=唯一键, value=重复的课程列表
    duplicate_records: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    for course in courses:
        unique_key = get_unique_key(course)
        teaching_class = course.get("教学班", "").strip()
        course_code = course.get("课程代码", "").strip()
        
        if unique_key not in unique_courses:
            # 第一次出现，保存
            unique_courses[unique_key] = course
        else:
            # 重复出现，记录
            duplicate_records[unique_key].append(course)
    
    # 打印重复报告
    if duplicate_records:
        print("\n" + "=" * 70)
        print("发现重复的课程（教学班 + 课程代码 都相同）:")
        print("=" * 70)
        
        with open(DUPLICATE_REPORT, "w", encoding="utf-8") as f:
            f.write("重复课程报告\n")
            f.write("=" * 70 + "\n")
            f.write("判断标准：教学班 和 课程代码 都相同\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for unique_key, duplicates in duplicate_records.items():
                # 解析唯一键
                parts = unique_key.split("||")
                teaching_class = parts[0] if len(parts) > 0 else "N/A"
                course_code = parts[1] if len(parts) > 1 else "N/A"
                
                print(f"\n[DUP] 重复课程:")
                print(f"   教学班: {teaching_class}")
                print(f"   课程代码: {course_code}")
                print(f"   出现次数: {len(duplicates) + 1} 次")
                
                f.write(f"\n重复课程:\n")
                f.write(f"  教学班: {teaching_class}\n")
                f.write(f"  课程代码: {course_code}\n")
                f.write(f"  出现次数: {len(duplicates) + 1} 次\n")
                f.write("  出现的文件:\n")
                
                # 打印第一次出现的信息
                first_course = unique_courses[unique_key]
                print(f"   第一次出现: {first_course.get('_source_file', 'unknown')}")
                print(f"     课程名称: {first_course.get('课程名称', 'N/A')}")
                print(f"     教师: {first_course.get('教师', 'N/A')}")
                
                f.write(f"    第一次出现: {first_course.get('_source_file', 'unknown')}\n")
                f.write(f"      课程名称: {first_course.get('课程名称', 'N/A')}\n")
                f.write(f"      教师: {first_course.get('教师', 'N/A')}\n")
                
                # 打印重复出现的信息
                for dup in duplicates:
                    print(f"   重复出现: {dup.get('_source_file', 'unknown')}")
                    print(f"     课程名称: {dup.get('课程名称', 'N/A')}")
                    print(f"     教师: {dup.get('教师', 'N/A')}")
                    
                    f.write(f"    重复出现: {dup.get('_source_file', 'unknown')}\n")
                    f.write(f"      课程名称: {dup.get('课程名称', 'N/A')}\n")
                    f.write(f"      教师: {dup.get('教师', 'N/A')}\n")
                
                print("   " + "- *" * 35)
        
        print(f"\n详细重复报告已保存至: {DUPLICATE_REPORT}")
    else:
        print("\n[OK] 没有发现重复的课程！所有课程的教学班+课程代码组合都是唯一的。")
    
    # 移除临时添加的 _source_file 字段
    result_courses = []
    for course in unique_courses.values():
        course_copy = course.copy()
        course_copy.pop("_source_file", None)
        result_courses.append(course_copy)
    
    print(f"\n去重前: {len(courses)} 条记录")
    print(f"去重后: {len(result_courses)} 条记录")
    print(f"去重数量: {len(courses) - len(result_courses)} 条")
    
    return result_courses


def save_to_json(courses: List[Dict[str, Any]], output_path: Path):
    """保存为JSON文件"""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(courses, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] JSON已保存: {output_path}")
    print(f"   文件大小: {output_path.stat().st_size / 1024:.2f} KB")


def save_to_csv(courses: List[Dict[str, Any]], output_path: Path):
    """保存为CSV文件"""
    if not courses:
        print("没有数据，跳过CSV导出")
        return
    
    # 定义所有字段
    fieldnames = [
        "教学班", "培养类型", "课程代码", "课程名称", "课程性质",
        "课程类别", "授课语言", "学分", "学时", "教师",
        "上课信息", "选课要求", "面向对象", "限制对象",
        "本科生容量/已选", "研究生容量/已选", "开课院系"
    ]
    
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for course in courses:
            # 确保每个字段都存在
            row = {field: course.get(field, "") for field in fieldnames}
            writer.writerow(row)
    
    print(f"[OK] CSV已保存: {output_path}")
    print(f"   记录数: {len(courses)}")


def generate_statistics(courses: List[Dict[str, Any]]):
    """生成统计信息"""
    print("\n" + "=" * 70)
    print("统计信息")
    print("=" * 70)
    
    # 按开课院系统计
    dept_count = defaultdict(int)
    for course in courses:
        dept = course.get("开课院系", "未知")
        dept_count[dept] += 1
    
    print("\n[STATS] 按开课院系统计（前10名）:")
    sorted_depts = sorted(dept_count.items(), key=lambda x: x[1], reverse=True)[:10]
    for dept, count in sorted_depts:
        print(f"   {dept}: {count} 门课程")
    
    # 按课程类别统计（修改这里）
    category_count = defaultdict(int)
    for course in courses:
        course_category = course.get("课程类别", "未知")
        category_count[course_category] += 1
    
    print("\n[STATS] 按课程类别统计:")
    for course_category, count in sorted(category_count.items(), key=lambda x: x[1], reverse=True):
        print(f"   {course_category}: {count} 门课程")
    
    # 按授课语言统计
    language_count = defaultdict(int)
    for course in courses:
        language = course.get("授课语言", "未知")
        language_count[language] += 1
    
    print("\n[STATS] 按授课语言统计:")
    for language, count in sorted(language_count.items(), key=lambda x: x[1], reverse=True):
        print(f"   {language}: {count} 门课程")
    
    # 总课程数
    print(f"\n[TOTAL] 总课程数（去重后）: {len(courses)}")


def main():
    # 设置输出重定向，同时输出到终端和文件
    tee = Tee(MERGE_REPORT)
    sys.stdout = tee
    
    try:
        print("=" * 70)
        print("课程表JSON合并工具")
        print("判断重复标准：教学班 + 课程代码 都相同")
        print("=" * 70)
        print(f"输入目录: {JSON_DIR}")
        print(f"输出JSON: {OUTPUT_JSON}")
        print(f"输出CSV: {OUTPUT_CSV}")
        print(f"合并报告: {MERGE_REPORT}")
        print("=" * 70)
        
        # 1. 加载所有JSON文件
        all_courses = load_all_json_files()
        
        if not all_courses:
            print("错误: 没有找到任何课程数据！")
            return
        
        # 2. 按教学班+课程代码去重
        unique_courses = deduplicate_by_class_and_code(all_courses)
        
        # 3. 保存JSON
        save_to_json(unique_courses, OUTPUT_JSON)
        
        # 4. 保存CSV
        save_to_csv(unique_courses, OUTPUT_CSV)
        
        # 5. 生成统计
        generate_statistics(unique_courses)
        
        print("\n" + "=" * 70)
        print("合并完成！")
        print(f"JSON文件: {OUTPUT_JSON}")
        print(f"CSV文件: {OUTPUT_CSV}")
        if Path(DUPLICATE_REPORT).exists():
            print(f"重复报告: {DUPLICATE_REPORT}")
        print(f"合并报告: {MERGE_REPORT}")
        print("=" * 70)
        
    finally:
        # 恢复标准输出并关闭文件
        sys.stdout = tee.terminal
        tee.close()
        print(f"\n[OK] 所有输出已保存到: {MERGE_REPORT}")


if __name__ == "__main__":
    main()