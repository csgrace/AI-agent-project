"""Prompt helpers for the document QA RAG pipeline."""
from __future__ import annotations

from typing import Sequence

from .models import SearchResult

def format_context(citations: Sequence[SearchResult]) -> str:
    if not citations: return "（未找到相关文档参考）"
    blocks = []
    for i, citation in enumerate(citations, 1):
        # Build context header from stored metadata
        context_parts: list[str] = []
        doc_title = getattr(citation, "doc_title", "") or ""
        section_path = getattr(citation, "section_path", "") or ""
        if doc_title:
            context_parts.append(f"[文档: {doc_title}]")
        if section_path:
            context_parts.append(f"[章节: {section_path}]")

        header = f"--- [Reference {i}] [Source: {citation.source_name}]"
        if context_parts:
            header += " " + " ".join(context_parts)
        header += " ---"

        blocks.append(f"{header}\n{citation.text.strip()}")
    return "\n\n".join(blocks)

def build_rag_prompt(
    question: str,
    citations: Sequence[SearchResult],
    *,
    max_score: float | None = None,
    query_kind: str | None = None,
    memory_context: str = "",
) -> str:
    context = format_context(citations)

    # Keep #sym:max_score as a stable control signal for downstream prompting.
    resolved_max_score = max_score if max_score is not None else (max([c.score for c in citations]) if citations else 0.0)
    resolved_query_kind = (query_kind or "unknown").strip().lower()

    # Inject conversation memory context if provided
    memory_section = f"\n\n{memory_context}" if memory_context else ""

    if resolved_max_score < 0.35:
        return (
            "<system>\n"
            "你是南方科技大学校园助手 SUSTech Campus Assistant。\n"
            "</system>\n\n"
            f"<mode>general_chat</mode>\n\n"
            f"<reasoning>\n"
            "知识库中没有找到与高置信度匹配的文档。"
            "因此你应基于自身知识友好回答，不要提及信息来源。\n"
            "</reasoning>\n"
            f"{memory_section}\n\n"
            f"<user_question>\n{question}\n</user_question>\n\n"
            "<output_rules>\n"
            "- 使用中文（简体中文）回答\n"
            "- 简短一段话，最多三句话\n"
            "- 不要问候、不要重复问题、不要使用问号结尾（除非是追问）\n"
            "- 保持简洁、自然的语气\n"
            "</output_rules>"
        )

    return (
        "<system>\n"
        "你是南方科技大学校园助手 SUSTech Campus Assistant。\n"
        "</system>\n\n"
        f"<mode>grounded_qa</mode>\n\n"
        f"<confidence>\n"
        f"max_score={resolved_max_score:.4f}, query_kind={resolved_query_kind}\n"
        f"</confidence>\n\n"
        "<task>\n"
        "基于提供的校园文档上下文回答用户问题。"
        "如果文档信息不足，如实说明并追问。\n"
        "</task>\n\n"
        f"<context>\n{context}\n</context>\n"
        f"{memory_section}\n\n"
        f"<user_question>\n{question}\n</user_question>\n\n"
        "<output_rules>\n"
        "- 答案严格基于上下文，不得编造\n"
        "- 最多三句话，优先最相关证据\n"
        "- 不要在答案中包含内嵌引用\n"
        "- 如果信息不足，只说明一次并提出一个具体追问\n"
        "- 不要重复同一事实、不要添加前言\n"
        "- 输出语言：简体中文\n"
        "</output_rules>"
    )


def build_query_routing_prompt(question: str, *, max_score: float | None = None) -> str:
    resolved_max_score = 0.0 if max_score is None else max_score
    return (
        "You are a routing assistant for a campus QA system.\n"
        f"#sym:max_score={resolved_max_score:.4f}\n\n"
        f"User question: {question}\n\n"
        "Your identity in this system is SUSTech Campus Assistant. Never call it Shenzhen University campus assistant.\n"
        "Decide whether the user is making casual conversation, asking about campus documents or knowledge that should be answered from a vector index, or whether the intent is unclear.\n"
        "Base your judgment on the meaning of the whole question, not on exact wording.\n"
        "Return exactly three lines and nothing else:\n"
        "intent=chat|document|unknown\n"
        "confidence=0.0-1.0\n"
        "reason=short explanation in Chinese\n"
    )


def build_answer_system_prompt(query_kind: str | None = None) -> str:
    resolved_query_kind = (query_kind or "unknown").strip().lower()
    if resolved_query_kind == "document":
        return (
            "You are SUSTech Campus Assistant. Answer in Chinese. "
            "Be concise, factual, and non-repetitive. "
            "Do not restate the question or repeat the same point. "
            "Use at most five short sentences. "
            "If evidence is insufficient, say so once and ask one specific follow-up question. "
            "Do not add greetings, sign-offs, headings, or filler."
        )

    return (
        "You are SUSTech Campus Assistant. Answer in Chinese. "
        "Be concise, natural, and non-repetitive. "
        "Do not restate the question or repeat the same point. "
        "Use at most two short sentences. "
        "Do not ask a follow-up question, do not use a question mark, and do not add greetings, sign-offs, headings, or filler. "
        "If the user is greeting or making small talk, reply with one brief statement of availability or friendliness only."
    )


def build_answerability_prompt(question: str, citations: Sequence[SearchResult]) -> str:
    context = format_context(citations)
    return (
        "You are a strict evidence judge for a campus QA system.\n"
        "Decide whether the provided evidence is sufficient to answer the user's question without guessing.\n"
        "If the evidence is incomplete, contradictory, or only weakly related, mark it as not answerable.\n\n"
        f"Question: {question}\n\n"
        f"Evidence:\n{context}\n\n"
        "Return exactly three lines and nothing else:\n"
        "answerable=true|false\n"
        "confidence=0.0-1.0\n"
        "reason=short explanation in Chinese\n"
    )


def build_clarification_prompt(question: str, citations: Sequence[SearchResult], reason: str) -> str:
    context = format_context(citations)
    return (
        "You are SUSTech Campus Assistant. The current evidence is not enough to answer safely.\n"
        f"Question: {question}\n\n"
        f"Evidence:\n{context}\n\n"
        f"Reason: {reason}\n\n"
        "Write a concise Chinese clarification reply.\n"
        "Do not invent facts. Do not answer the original question directly.\n"
        "Ask one specific follow-up question that would help complete the answer, or say the evidence is insufficient and ask for the missing detail.\n"
        "Do not use headings or bullet points."
    )
