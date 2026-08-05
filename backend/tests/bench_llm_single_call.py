"""独立测速脚本：模拟 extract_keywords 的单次 LLM 调用，测量耗时。

复现的是 llm_service.py 中 `extract_keywords` 方法的调用逻辑：
- 模型: qwen3.5-plus (来自 llm_config.json smart tier)
- temperature: 0.0
- max_tokens: 120
- API: DashScope (兼容 OpenAI 格式)
"""

import json
import os
import sys
import time
from pathlib import Path

# 确保能导入项目模块
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from openai import OpenAI


def load_config() -> dict:
    config_path = PROJECT_ROOT / "resources" / "llm_config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_extract_keywords_prompt(question: str, texts: list[str], limit: int = 5) -> str:
    """与 llm_service.py extract_keywords 完全一致的 prompt 构造逻辑."""
    sample = "\n---\n".join(texts[:3])
    return (
        f"给定用户问题：\n{question}\n\n"
        f"以及来自同一来源的文本片段（用\n---\n分隔）：\n{sample}\n\n"
        f"请提取不超过 {limit} 个最能帮助回答该问题的关键词或短语，返回 JSON 数组，例如：[\"关键词1\", \"关键词2\"]。"
    )


def main():
    config = load_config()
    api_key = config["api_key"]
    base_url = config["base_url"]
    smart_tier = config["tiers"]["smart"]
    model = smart_tier["model"]

    print(f"=== LLM 单次调用测速 ===")
    print(f"Provider: {config['provider']}")
    print(f"Base URL: {base_url}")
    print(f"Model:     {model}")
    print(f"Temperature: 0.0")
    print(f"Max Tokens:  120")
    print()

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 模拟一段 extract_keywords 的典型输入（来自校园助手的真实场景）
    question = "软件工程专业有哪些必修课？"
    texts = [
        "软件工程专业必修课程包括：数据结构与算法分析、操作系统、计算机网络、软件工程导论、数据库系统原理。这些课程是软件工程专业的核心基础课程。",
        "软件工程专业培养方案要求学生修读不少于128学分，其中通识必修课38学分，专业必修课52学分，专业选修课20学分，实践环节18学分。",
        "2023级软件工程专业必修课列表：CS201 数据结构与算法分析、CS202 计算机组成原理、CS301 操作系统、CS302 计算机网络、SE301 软件工程导论、SE401 软件测试与质量保证。",
    ]

    prompt = build_extract_keywords_prompt(question, texts, limit=5)

    print(f"Prompt 长度: {len(prompt)} chars")
    print(f"Prompt 内容预览:\n{prompt[:300]}...\n")

    # ── 测速：单次调用 ──
    print(">>> 开始调用 LLM...")
    t_start = time.perf_counter()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=120,
        )
        t_end = time.perf_counter()
        elapsed = t_end - t_start

        answer = response.choices[0].message.content.strip()
        print(f">>> 调用完成，耗时: {elapsed:.2f} 秒 ({elapsed/60:.2f} 分钟)")
        print(f"    响应长度: {len(answer)} chars")
        print(f"    响应内容: {answer}")
        print()

        # 获取 token 用量（如果 API 返回）
        usage = response.usage
        if usage:
            print(f"Token 用量: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")

    except Exception as e:
        t_end = time.perf_counter()
        elapsed = t_end - t_start
        print(f">>> 调用失败，耗时: {elapsed:.2f} 秒")
        print(f"    错误: {type(e).__name__}: {e}")
        return

    # ── 估算：如果像日志那样有 5 次 extract_keywords ──
    print()
    print("=== 耗时推算 ===")
    print(f"单次 extract_keywords 调用: {elapsed:.1f} 秒")
    print(f"日志中 5 次 extract_keywords 预期耗时: {elapsed * 5:.1f} 秒 ({elapsed * 5 / 60:.1f} 分钟)")
    print(f"加上 routing(1) + answerability(1) + answer(1) = 额外 3 次调用")
    print(f"总计 8 次调用预期耗时:  {elapsed * 8:.1f} 秒 ({elapsed * 8 / 60:.1f} 分钟)")
    print()
    print("💡 建议：将 extract_keywords 的多源调用改为并行（asyncio 或 concurrent.futures），")
    print("   可将该阶段耗时从 N×单次 压缩到 ≈单次调用时间。")


if __name__ == "__main__":
    main()
