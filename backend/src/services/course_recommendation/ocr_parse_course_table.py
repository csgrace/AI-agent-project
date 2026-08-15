"""
课程表OCR解析服务
使用阿里云千问Vision API将课程表图片转换为结构化JSON
"""

from pathlib import Path
import base64
import json
import time
import re
from typing import List, Dict, Any
from openai import OpenAI

from ...services.llm_config import LLMConfig

# ==========================================================
# API 配置 — 从 LLMConfig 的 vision 档位获取
# ==========================================================
cfg = LLMConfig.get_instance()
client = cfg.build_openai_client(use_fallback=False)
_model = cfg.get_tier_model("vision", use_fallback=False)

if client is None:
    raise ValueError(
        "找不到 API Key 配置。请在个人中心设置 API Key，"
        "或在 backend/.env 中设置 DASHSCOPE_API_KEY。"
    )

# ==========================================================
# 路径配置
# ==========================================================
DATA_DIR = BACKEND_ROOT / "data" / "tis_download" / "full_course_table"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
JSON_DIR = DATA_DIR / "json"

JSON_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================================
# 图片编码
# ==========================================================
def encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ==========================================================
# 调用千问 Vision API
# ==========================================================
def qwen_vision_ocr(image_path: Path) -> List[Dict[str, Any]]:
    """
    使用千问视觉模型识别课程表图片，返回课程列表
    """
    img_b64 = encode_image(image_path)
    suffix = image_path.suffix.lower()
    mime_type = "image/png" if suffix == ".png" else "image/jpeg"
    
    prompt = """请从图片中提取所有课程信息，输出一个JSON数组。

每个课程对象必须包含以下字段（图片中没有的信息留空字符串）：
{
  "教学班": "",
  "培养类型": "",
  "课程代码": "",
  "课程名称": "",
  "课程性质": "",
  "课程类别": "",
  "授课语言": "",
  "学分": "",
  "学时": "",
  "教师": "",
  "上课信息": "",
  "选课要求": "",
  "面向对象": "",
  "限制对象": "",
  "本科生容量/已选": "",
  "研究生容量/已选": "",
  "开课院系": ""
}

【重要规则】：
- 每个不同的教学班必须作为一个独立的课程对象输出
- 即使课程代码相同，只要教学班名称不同，就要分开输出
- 例如："大学地球科学.02班"和"大学地球科学.03班"是两个不同的对象

要求：
- 输出必须是合法的JSON数组
- 不要markdown格式
- 不要任何解释文字
- 图片中有多少门课程（按教学班区分），数组里就放多少个对象
"""
    
    response = client.chat.completions.create(
        model=_model,
        # qwen3.6-plus
        # qwen3-vl-32b-thinking
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{img_b64}"
                        }
                    }
                ]
            }
        ],
        temperature=0,
        timeout=120,
    )
    
    content = response.choices[0].message.content
    
    # 提取JSON
    json_match = re.search(r'\[[\s\S]*\]', content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except:
            pass
    
    # 直接尝试解析
    try:
        return json.loads(content)
    except:
        raise ValueError(f"无法解析JSON: {content[:200]}")


def split_merged_teaching_classes(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将教学班字段中合并的多个班级拆分成独立的课程对象
    例如："大学地球科学.02班-双语, 大学地球科学.03班-双语" -> 拆成两个对象
    """
    result = []
    
    for course in courses:
        teaching_class = course.get("教学班", "")
        
        # 检查是否包含多个班级（用逗号分隔）
        if "，" in teaching_class or "," in teaching_class:
            # 分割多个班级名称
            class_names = re.split(r'[，,]\s*', teaching_class)
            
            # 获取其他字段
            course_code = course.get("课程代码", "")
            course_name = course.get("课程名称", "")
            course_type = course.get("课程性质", "")
            course_category = course.get("课程类别", "")
            language = course.get("授课语言", "")
            credits = course.get("学分", "")
            hours = course.get("学时", "")
            teachers = course.get("教师", "")
            schedule = course.get("上课信息", "")
            requirements = course.get("选课要求", "")
            target_audience = course.get("面向对象", "")
            restrictions = course.get("限制对象", "")
            undergrad_capacity = course.get("本科生容量/已选", "")
            grad_capacity = course.get("研究生容量/已选", "")
            department = course.get("开课院系", "")
            training_type = course.get("培养类型", "")
            
            # 为每个班级创建独立的对象
            for class_name in class_names:
                class_name = class_name.strip()
                if class_name:
                    new_course = {
                        "教学班": class_name,
                        "培养类型": training_type,
                        "课程代码": course_code,
                        "课程名称": course_name,
                        "课程性质": course_type,
                        "课程类别": course_category,
                        "授课语言": language,
                        "学分": credits,
                        "学时": hours,
                        "教师": teachers,
                        "上课信息": schedule,
                        "选课要求": requirements,
                        "面向对象": target_audience,
                        "限制对象": restrictions,
                        "本科生容量/已选": undergrad_capacity,
                        "研究生容量/已选": grad_capacity,
                        "开课院系": department
                    }
                    result.append(new_course)
        else:
            # 没有合并，直接添加
            result.append(course)
    
    return result


def split_merged_teachers_and_schedules(courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    如果同一个班级有多个教师或多个上课时间段，拆分成多个对象
    注意：这个函数只在必要时使用，按需拆分
    """
    result = []
    
    for course in courses:
        teachers = course.get("教师", "")
        schedule = course.get("上课信息", "")
        
        # 检查是否有多组上课信息（用分号分隔）
        if "；" in schedule or ";" in schedule:
            schedule_parts = re.split(r'[;；]\s*', schedule)
            
            # 检查教师是否也有多个（用逗号分隔）
            teacher_list = re.split(r'[，,]\s*', teachers) if teachers else []
            
            # 如果教师数量和上课时间段数量匹配，则一一对应
            if len(teacher_list) == len(schedule_parts) and len(teacher_list) > 1:
                for i, (teacher, sched) in enumerate(zip(teacher_list, schedule_parts)):
                    new_course = course.copy()
                    new_course["教师"] = teacher
                    new_course["上课信息"] = sched
                    # 如果是第一个，保留原教学班名称；后续添加后缀
                    if i > 0:
                        new_course["教学班"] = f"{course.get('教学班', '')}-{i+1}"
                    result.append(new_course)
            else:
                # 不匹配或只有一组教师，上课信息合并到一个对象中
                result.append(course)
        else:
            result.append(course)
    
    return result


def normalize_course_data(parsed_data: Any) -> List[Dict[str, Any]]:
    """
    标准化课程数据，确保所有字段都存在
    重点：拆分校合并的教学班
    """
    required_fields = [
        "教学班", "培养类型", "课程代码", "课程名称", "课程性质",
        "课程类别", "授课语言", "学分", "学时", "教师",
        "上课信息", "选课要求", "面向对象", "限制对象",
        "本科生容量/已选", "研究生容量/已选", "开课院系"
    ]
    
    if not isinstance(parsed_data, list):
        if isinstance(parsed_data, dict):
            parsed_data = [parsed_data]
        else:
            return []
    
    # 先确保每个对象都有所有字段
    normalized_courses = []
    for course in parsed_data:
        if not isinstance(course, dict):
            continue
        
        normalized_course = {}
        for field in required_fields:
            value = course.get(field, "")
            if value is None:
                value = ""
            if isinstance(value, str):
                value = re.sub(r'\s+', ' ', value).strip()
                if field == "上课信息":
                    value = clean_schedule_info(value)
                if field == "教师":
                    value = clean_teacher_names(value)
            normalized_course[field] = value
        
        normalized_courses.append(normalized_course)
    
    # 拆分合并的教学班（最关键的一步）
    split_courses = split_merged_teaching_classes(normalized_courses)
    
    # 可选：拆分教师和上课信息（如果需要一一对应）
    # split_courses = split_merged_teachers_and_schedules(split_courses)
    
    return split_courses


def clean_schedule_info(text: str) -> str:
    """
    清理上课信息字段，移除混入的"选课要求"等内容
    """
    if not text:
        return ""
    
    patterns = [
        r'选课要求:.*$',
        r'备注:.*$',
        r'注:.*$',
        r'要求:.*$',
        r'主任务:.*$',
        r'课内实验:.*$',
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    text = re.sub(r'[;；]\s*[;；]', '；', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.rstrip(';；')
    
    return text


def clean_teacher_names(text: str) -> str:
    """
    清理教师名字字段
    """
    if not text:
        return ""
    
    text = re.sub(r'上课信息:.*$', '', text)
    text = re.sub(r'选课要求:.*$', '', text)
    text = re.sub(r'主任务:.*$', '', text)
    text = re.sub(r'课内实验:.*$', '', text)
    
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.replace(',', '，').replace(';', '，')
    
    names = [name.strip() for name in text.split('，') if name.strip()]
    unique_names = list(dict.fromkeys(names))
    text = '，'.join(unique_names)
    
    return text


# ==========================================================
# 单张图片处理
# ==========================================================
def process_single_image(image_path: Path) -> Dict[str, Any]:
    """处理单张课程表图片，保存为JSON文件"""
    result = {
        "image_name": image_path.name,
        "success": False,
        "data": None,
        "error": None
    }
    
    try:
        courses = qwen_vision_ocr(image_path)
        result["success"] = True
        result["data"] = courses
        
        # 保存JSON文件
        out_file = JSON_DIR / f"{image_path.stem}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(courses, f, ensure_ascii=False, indent=2)
        result["saved_to"] = str(out_file)
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


# ==========================================================
# 批量处理（带断点续传）
# ==========================================================
def batch_process_all_images(delay: float = 0.3):
    """批量处理所有图片，跳过已存在的JSON文件"""
    
    # 获取所有图片，按数字排序
    all_images = sorted(SCREENSHOT_DIR.glob("page_*.png"))
    
    if not all_images:
        print(f"错误: {SCREENSHOT_DIR} 中没有找到图片")
        return
    
    # 检查哪些图片已经处理过
    processed = set()
    for json_file in JSON_DIR.glob("page_*.json"):
        processed.add(json_file.stem + ".png")
    
    # 待处理的图片
    to_process = [img for img in all_images if img.name not in processed]
    
    print("=" * 60)
    print(f"总共 {len(all_images)} 张图片")
    print(f"已完成 {len(processed)} 张")
    print(f"待处理 {len(to_process)} 张")
    print("=" * 60)
    
    if not to_process:
        print("所有图片都已处理完成！")
        return
    
    success_count = 0
    fail_count = 0
    
    for idx, img in enumerate(to_process, 1):
        print(f"\n[{idx}/{len(to_process)}] 处理: {img.name}")
        
        result = process_single_image(img)
        
        if result["success"]:
            success_count += 1
            course_count = len(result["data"])
            print(f"  [OK] 成功，识别到 {course_count} 门课程")
            print(f"  [OK] 保存至: {result['saved_to']}")
        else:
            fail_count += 1
            print(f"  [FAIL] 失败: {result['error'][:100]}")
        
        if idx < len(to_process):
            time.sleep(delay)
    
    print("\n" + "=" * 60)
    print(f"处理完成！")
    print(f"成功: {success_count} 张")
    print(f"失败: {fail_count} 张")
    print(f"累计完成: {len(processed) + success_count}/{len(all_images)} 张")
    print("=" * 60)


# ==========================================================
# 主入口
# ==========================================================
if __name__ == "__main__":
    batch_process_all_images()