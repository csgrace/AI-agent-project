"""LLM prompt templates for content summarization and quiz generation."""

import json

# ===== Summary Prompts (T3.3) =====

SUMMARY_SYSTEM_PROMPT = """你是一位专业的教学助手，负责为学生总结课程材料。你的总结需要：
- 保留关键概念、术语和概念间关系
- 根据内容长度自适应调整总结篇幅
- 使用清晰、准确的中文表达
- 不添加原文中没有的信息"""

SUMMARY_STYLE_TEMPLATES = {
    "concise": """请对以下教学内容进行**简洁总结**，用1个段落概括核心要点。

要求：
- 仅包含最重要的概念或结论
- 控制在 100-200 字以内
- 适合快速复习

教学内容：
{content}

简洁总结：""",

    "detailed": """请对以下教学内容进行**详细总结**，结构完整、层次分明。

要求：
- 全面覆盖所有重要知识点
- 按逻辑顺序组织内容
- 保留关键术语和定义
- 解释概念间的关系
- 篇幅根据内容量适当调整

教学内容：
{content}

详细总结：""",

    "outline": """请将以下教学内容整理为**要点提纲**，使用项目符号列表形式。

要求：
- 使用多级缩进表现层次结构
- 每个要点简洁明了
- 保留关键术语

教学内容：
{content}

要点提纲：""",

    "mind_map": """请将以下教学内容转换为**思维导图格式**的结构化文本。

要求：
- 使用缩进表示层级关系（2空格缩进）
- 根节点为课程标题
- 一级节点为主要主题
- 二级节点为子概念或细节
- 保留关键术语和关系

教学内容：
{content}

思维导图格式：
思维导图
""",
}


# ===== Question Generation Prompts (T3.5) =====

QUESTION_SYSTEM_PROMPT = """你是一位专业的教学评估助手，负责根据教学内容生成测验题目。你的题目需要：
- 考查学生对概念的理解而非死记硬背
- 题目表述清晰、无歧义
- 提供准确的答案和教学性解释
- 使用中文出题"""

QUESTION_STYLE_PROMPTS = {
    "multiple_choice": """请根据以下教学内容生成{num_questions}道**单选题**。

题型要求：
- 每题4个选项（A、B、C、D）
- 只有1个正确答案
- 干扰项应合理且有迷惑性
- 考查理解能力而非事实记忆{extra_difficulty_instruction}

教学内容：
{content}

请按以下JSON格式输出，不要有其他内容：
{{
  "questions": [
    {{
      "type": "multiple_choice",
      "question_text": "题目内容",
      "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
      "correct_answer": "A",
      "difficulty": "easy/medium/hard"
    }}
  ]
}}""",

    "fill_in_blank": """请根据以下教学内容生成{num_questions}道**填空题**。

题型要求：
- 用"____"表示填空位置
- 每个空应有唯一正确答案
- 考查关键术语或概念{extra_difficulty_instruction}

教学内容：
{content}

请按以下JSON格式输出，不要有其他内容：
{{
  "questions": [
    {{
      "type": "fill_in_blank",
      "question_text": "带有____的题目",
      "correct_answer": "标准答案",
      "difficulty": "easy/medium/hard"
    }}
  ]
}}""",

    "true_false": """请根据以下教学内容生成{num_questions}道**判断题**。

题型要求：
- 判断给定陈述的对错
- 考查对概念的理解和辨别能力{extra_difficulty_instruction}

教学内容：
{content}

请按以下JSON格式输出，不要有其他内容：
{{
  "questions": [
    {{
      "type": "true_false",
      "question_text": "陈述内容",
      "correct_answer": "对/错",
      "difficulty": "easy/medium/hard"
    }}
  ]
}}""",

    "short_answer": """请根据以下教学内容生成{num_questions}道**简答题**。

题型要求：
- 需要学生进行简短文字作答
- 考查对概念的理解和综合能力{extra_difficulty_instruction}

教学内容：
{content}

请按以下JSON格式输出，不要有其他内容：
{{
  "questions": [
    {{
      "type": "short_answer",
      "question_text": "问题内容",
      "correct_answer": "标准答案要点",
      "difficulty": "easy/medium/hard"
    }}
  ]
}}""",
}


# ===== Explanation Enhancement Prompts (T3.7) =====

EXPLANATION_SYSTEM_PROMPT = """你是一位有耐心的教学导师，负责为学生提供题目的详细解答和辅导。你的解释需要：
- 具有教育性，帮助学生理解而不是只给答案
- 对于选择题：解释每个选项为什么对或错
- 对于其他题型：提供评分要点和答题思路
- 使用友好、鼓励的语气"""

EXPLANATION_PROMPT = """请为以下题目提供**详细的答案解释**。

题目信息：
- 题目：{question_text}
- 题型：{question_type}
- 正确答案：{correct_answer}
{f1}

要求：
{explanation_requirements}

请按以下JSON格式输出，不要有其他内容：
{expected_output_format}
"""


def build_explanation_prompt(
    question_text: str,
    question_type: str,
    correct_answer: str,
    options: list[str] | None = None,
) -> str:
    """Build the explanation prompt for a given question.

    Args:
        question_text: The question text.
        question_type: Type of question (multiple_choice, fill_in_blank, true_false, short_answer).
        correct_answer: The correct answer.
        options: List of options (for multiple choice).

    Returns:
        Formatted prompt string.
    """
    f1 = ""
    if options:
        f1 = f"- 选项：{', '.join(options)}"

    if question_type == "multiple_choice":
        requirements = ("- 解释为什么正确答案是正确的\n"
                        "- 解释每个错误选项错在哪里（为什么具有迷惑性）\n"
                        "- 提示学生如何避免被类似干扰项误导")
        expected = """{
  "explanations": {
    "correct": "正确答案是X，因为...",
    "incorrect": {
      "A": "A选项错误是因为...",
      "B": ...,
      "C": ...,
      "D": ...
    }
  }
}"""
    elif question_type == "true_false":
        requirements = ("- 解释为什么这个陈述是对的或错的\n"
                        "- 如果是错的，给出正确的表述")
        expected = """{
  "explanations": {
    "correct": "这个陈述是（对/错）的，因为...",
    "correction": "（如果是错的）正确的表述应该是..."
  }
}"""
    elif question_type == "fill_in_blank":
        requirements = ("- 解释为什么这个答案是正确答案\n"
                        "- 提示哪些上下文线索可以帮助得出答案")
        expected = """{
  "explanations": {
    "correct": "答案是...，因为...",
    "hints": "可以从...这些上下文线索推断出答案"
  }
}"""
    else:  # short_answer
        requirements = ("- 提供标准答案示例\n"
                        "- 给出评分要点和分值建议\n"
                        "- 提供答题思路指导")
        expected = """{
  "explanations": {
    "model_answer": "完整的标准答案示例...",
    "scoring_points": ["要点1（分值）", "要点2（分值）"],
    "approach": "答题思路：..."
  }
}"""

    return EXPLANATION_PROMPT.format(
        question_text=question_text,
        question_type=question_type,
        correct_answer=correct_answer,
        f1=f1,
        explanation_requirements=requirements,
        expected_output_format=expected,
    )


# ===== Difficulty Instructions (T3.6) =====

DIFFICULTY_INSTRUCTIONS = {
    "easy": "难度要求：简单 —— 仅考查基础术语和事实识记，直接来自原文。",
    "medium": "难度要求：中等 —— 考查概念理解及概念间关系，需要一定推理。",
    "hard": "难度要求：困难 —— 考查应用与综合分析，需要将知识应用到新场景。",
}


def build_summary_prompt(content: str, style: str) -> tuple[str, str]:
    """Build the prompt pair for summary generation.

    Args:
        content: The structured content to summarize.
        style: Summary style (concise, detailed, outline, mind_map).

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    template = SUMMARY_STYLE_TEMPLATES.get(style, SUMMARY_STYLE_TEMPLATES["concise"])
    return SUMMARY_SYSTEM_PROMPT, template.format(content=content)


def build_question_prompt(
    content: str,
    question_type: str,
    num_questions: int = 5,
    difficulty: str | None = None,
) -> tuple[str, str]:
    """Build the prompt pair for question generation.

    Args:
        content: The structured content to generate questions from.
        question_type: Type of question (multiple_choice, fill_in_blank, true_false, short_answer).
        num_questions: Number of questions to generate.
        difficulty: Difficulty level (easy, medium, hard) or None for mixed.

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    template = QUESTION_STYLE_PROMPTS.get(question_type, QUESTION_STYLE_PROMPTS["multiple_choice"])

    extra_difficulty_instruction = ""
    if difficulty and difficulty in DIFFICULTY_INSTRUCTIONS:
        extra_difficulty_instruction = f"\n{DIFFICULTY_INSTRUCTIONS[difficulty]}"

    return QUESTION_SYSTEM_PROMPT, template.format(
        content=content,
        num_questions=num_questions,
        extra_difficulty_instruction=extra_difficulty_instruction,
    )


# ===== Grading Prompts =====

GRADE_SYSTEM_PROMPT = """你是一位教学评分助手，负责对学生的简答题答案进行评分和反馈。
评分标准：
1. 对照参考答案和评分要点，判断学生答案是否正确
2. 给出分数（0-100分）和等级（correct, partial, incorrect）
3. 提供有建设性的反馈，指出正确之处和不足之处
4. 反馈要具有教育性，帮助学生改进"""


def build_grade_prompt(
    question_text: str,
    student_answer: str,
    correct_answer: str,
    explanations: dict | None = None,
) -> str:
    """Build the prompt for grading a short answer question.

    Args:
        question_text: The question text.
        student_answer: The student's answer.
        correct_answer: The reference correct answer.
        explanations: Optional explanations dict with grading criteria.

    Returns:
        The user prompt for the LLM.
    """
    prompt = f"请评分以下简答题：\n\n题目：{question_text}\n\n参考答案：{correct_answer}\n\n学生答案：{student_answer}\n\n"
    if explanations:
        prompt += f"评分参考：{json.dumps(explanations, ensure_ascii=False)}\n\n"
    prompt += """请以JSON格式返回评分结果：
{{
  "score": 0-100,
  "level": "correct" 或 "partial" 或 "incorrect",
  "feedback": "详细的反馈意见"
}}"""
    return prompt
