"""Prompt helpers for the document QA RAG pipeline."""
from __future__ import annotations

from typing import Sequence

from .models import SearchResult

def format_context(citations: Sequence[SearchResult]) -> str:
    if not citations: return "（未找到相关文档参考）"
    blocks = []
    for i, citation in enumerate(citations, 1):
        blocks.append(f"--- [Reference {i}] [Source: {citation.source_name}] ---\n{citation.text.strip()}")
    return "\n\n".join(blocks)

def build_rag_prompt(
    question: str,
    citations: Sequence[SearchResult],
    *,
    max_score: float | None = None,
    query_kind: str | None = None,
) -> str:
    context = format_context(citations)

    # Keep #sym:max_score as a stable control signal for downstream prompting.
    resolved_max_score = max_score if max_score is not None else (max([c.score for c in citations]) if citations else 0.0)
    resolved_query_kind = (query_kind or "unknown").strip().lower()

    if resolved_max_score < 0.35:
        return (
            "Role: SUSTech Campus Assistant (General Chat Mode)\n"
            f"#sym:max_score={resolved_max_score:.4f}\n"
            f"#sym:query_kind={resolved_query_kind}\n\n"
            f"Question: {question}\n\n"
            "Task: Answer the user\"s question directly using your internal knowledge. "
            "Since no high-quality PDF matches were found, be a helpful campus assistant. "
            "Your identity is SUSTech Campus Assistant. Do NOT translate or rename it as any other university assistant. "
            "Answer in one short paragraph. Avoid greetings, hedging, repeated wording, and follow-up questions. "
            "Answer in Chinese (简体中文)."
        )

    return (
        "Role: SUSTech Campus Assistant (Grounded QA Mode)\n"
        f"#sym:max_score={resolved_max_score:.4f}\n"
        f"#sym:query_kind={resolved_query_kind}\n\n"
        "Input Data (Context from Campus PDFs):\n"
        f"{context}\n\n"
        f"Question: {question}\n\n"
        "Task:\n"
        "You are SUSTech Campus Assistant. Do NOT rename yourself as any other university assistant.\n"
        "Answer strictly based on the provided context.\n"
        "Give the answer in one short paragraph, or at most three short sentences.\n"
        "Prioritize the most directly relevant evidence. Do NOT include inline citations like (Source: ...) in your answer — sources are shown separately in the UI.\n"
        "If the context is insufficient, say so once and ask one specific follow-up question.\n"
        "Do not repeat the same fact with different wording, do not add a preface, and do not use headings or numbered lists unless the answer truly requires a list.\n"
        "Never fabricate policies, dates, scores, deadlines, or procedures not present in context.\n"
        "Output MUST be in Chinese (简体中文).\n"
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
