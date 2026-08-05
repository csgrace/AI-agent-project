"""Runner wrapper for scheduler create_agent execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from langchain_core.load import dumpd, load
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage

DEBUG = True

def debug_log(msg: str) -> None:
    """输出调试信息"""
    if DEBUG:
        print(f"[DEBUG] {msg}")


class AgentRunner:
    """Manage message state around a compiled create_agent instance."""

    def __init__(self, compiled_agent: Any, *, max_steps: int = 8, stream_tokens: bool = False) -> None:
        self.compiled_agent = compiled_agent
        self.max_steps = max_steps
        self.stream_tokens = stream_tokens
        self.messages: List[BaseMessage] = []

    def run_turn(self, user_text: str) -> Dict[str, Any]:
        """Run one user turn and return normalized result payload."""
        final_event: Dict[str, Any] = {
            "event": "final",
            "reply": "",
            "finished": False,
            "steps": 0,
            "tool_calls": 0,
            "requires_commit": False,
        }
        for event in self.run_turn_stream(user_text):
            if event.get("event") == "final":
                final_event = event

        return {
            "reply": final_event.get("reply", ""),
            "finished": bool(final_event.get("finished", False)),
            "steps": int(final_event.get("steps", 0)),
            "tool_calls": int(final_event.get("tool_calls", 0)),
            "requires_commit": bool(final_event.get("requires_commit", False)),
        }

    def run_turn_stream(self, user_text: str) -> Generator[Dict[str, Any], None, None]:
        """Run one user turn and yield normalized streaming events."""
        previous_len = len(self.messages)
        self.messages.append(HumanMessage(content=user_text))
        debug_log(f"[run_turn_stream] 开始处理用户输入: {user_text[:100]}...")
        debug_log(f"[run_turn_stream] 消息历史长度: {previous_len}")

        try:
            config = {"recursion_limit": max(50, self.max_steps * 5)}
            debug_log(f"[run_turn_stream] 配置: recursion_limit={config['recursion_limit']}")
            requires_commit = False
            intermediate_ai_ids: set = set()

            if hasattr(self.compiled_agent, "stream"):
                debug_log("[run_turn_stream] 使用 stream 模式")
                last_messages = self.messages
                cursor = previous_len + 1

                for chunk in self.compiled_agent.stream(
                    {"messages": self.messages},
                    config=config,
                    stream_mode=["values", "custom"],
                ):
                    mode = "values"
                    payload = chunk
                    if isinstance(chunk, tuple) and len(chunk) == 2:
                        mode, payload = chunk
                    debug_log(f"[run_turn_stream] 收到 chunk, mode={mode}")

                    if mode == "custom":
                        if isinstance(payload, dict):
                            tool_name = str(payload.get("tool", ""))
                            stage = str(payload.get("stage", ""))
                            debug_log(f"[run_turn_stream] custom 事件: tool={tool_name}, stage={stage}")

                            if tool_name == "execute_script":
                                if stage == "output":
                                    # 脚本逐行输出 → 专用事件，前端渲染 terminal
                                    debug_log(f"[run_turn_stream] YIELD script_output stream={payload.get('stream')} msg_len={len(str(payload.get('message', '')))}")
                                    yield {
                                        "event": "script_output",
                                        "execution_id": str(payload.get("execution_id", "")),
                                        "stream": str(payload.get("stream", "stdout")),
                                        "message": str(payload.get("message", "")),
                                    }
                                elif stage in ("running", "completed"):
                                    # 执行开始 / 完成 → terminal 面板控制
                                    debug_log(f"[run_turn_stream] YIELD script_execution stage={stage} name={payload.get('name')}")
                                    yield {
                                        "event": "script_execution",
                                        "execution_id": str(payload.get("execution_id", "")),
                                        "stage": stage,
                                        "name": str(payload.get("name", "")),
                                        "message": str(payload.get("message", "")),
                                        "returncode": payload.get("returncode"),
                                        "ok": payload.get("ok"),
                                    }
                                else:
                                    # 其他 execute_script 阶段 → 普通进度
                                    yield {
                                        "event": "tool_progress",
                                        "tool_name": tool_name,
                                        "stage": stage,
                                        "message": str(payload.get("message", "")),
                                        **{k: v for k, v in payload.items()
                                           if k not in ("tool", "stage", "message")},
                                    }
                            else:
                                # 其他工具的进度事件 → 保持原样
                                yield {
                                    "event": "tool_progress",
                                    "tool_name": tool_name,
                                    "stage": stage,
                                    "message": str(payload.get("message", "")),
                                    **{k: v for k, v in payload.items()
                                       if k not in ("tool", "stage", "message")},
                                }
                        else:
                            yield {
                                "event": "tool_progress",
                                "tool_name": "",
                                "stage": "",
                                "message": str(payload),
                            }
                        continue

                    if not isinstance(payload, dict):
                        debug_log(f"[run_turn_stream] payload 不是 dict 类型: {type(payload)}")
                        continue

                    if "requires_commit" in payload:
                        requires_commit = bool(payload.get("requires_commit"))
                        debug_log(f"[run_turn_stream] requires_commit = {requires_commit}")

                    chunk_messages = list(payload.get("messages", last_messages))
                    debug_log(f"[run_turn_stream] chunk_messages 长度: {len(chunk_messages)}, cursor={cursor}")
                    for message in chunk_messages[cursor:]:
                        if isinstance(message, AIMessage):
                            tool_calls = list(getattr(message, "tool_calls", []) or [])
                            debug_log(f"[run_turn_stream] AIMessage: tool_calls数量={len(tool_calls)}")

                            for tool_call in tool_calls:
                                debug_log(f"[run_turn_stream] 发送 tool_call: {tool_call.get('name')}")
                                yield {
                                    "event": "tool_call",
                                    "tool_name": tool_call.get("name", ""),
                                    "tool_args": tool_call.get("args", {}),
                                }

                            content = self._extract_content(message)
                            if content.strip() and tool_calls:
                                debug_log(f"[run_turn_stream] 发送 thought: {content[:100]}...")
                                intermediate_ai_ids.add(id(message))
                                yield {
                                    "event": "thought",
                                    "text": content,
                                }

                        elif isinstance(message, ToolMessage):
                            tool_content = self._extract_tool_content(message)
                            tool_name = getattr(message, "name", "unknown")
                            debug_log(f"[run_turn_stream] YIELD tool_result tool={tool_name} content_len={len(tool_content)}")
                            yield {
                                "event": "tool_result",
                                "tool_call_id": message.tool_call_id,
                                "tool_output": tool_content,
                            }

                    cursor = len(chunk_messages)
                    last_messages = chunk_messages

                self.messages = last_messages
            else:
                debug_log("[run_turn_stream] 使用 invoke 模式")
                result = self.compiled_agent.invoke(
                    {"messages": self.messages},
                    config=config,
                )
                self.messages = list(result.get("messages", self.messages))
                requires_commit = bool(result.get("requires_commit", False))

                new_messages = self.messages[previous_len + 1 :]
                for message in new_messages:
                    if isinstance(message, AIMessage):
                        tool_calls = list(getattr(message, "tool_calls", []) or [])

                        for tool_call in tool_calls:
                            yield {
                                "event": "tool_call",
                                "tool_name": tool_call.get("name", ""),
                                "tool_args": tool_call.get("args", {}),
                            }

                        content = self._extract_content(message)
                        if content.strip() and tool_calls:
                            intermediate_ai_ids.add(id(message))
                            yield {
                                "event": "thought",
                                "text": content,
                            }

                    elif isinstance(message, ToolMessage):
                        yield {
                            "event": "tool_result",
                            "tool_call_id": message.tool_call_id,
                            "tool_output": self._extract_tool_content(message),
                        }

            final_ai_message = self._last_ai_message_without_tool_calls(self.messages)
            reply = self._extract_content(final_ai_message) if final_ai_message else ""
            
            # 计算工具调用次数
            tool_calls_count = 0
            for msg in self.messages:
                if isinstance(msg, AIMessage):
                    tool_calls = list(getattr(msg, "tool_calls", []) or [])
                    tool_calls_count += len(tool_calls)
            
            # 如果最终回复为空，提供默认完成消息
            if not reply.strip() and tool_calls_count > 0:
                reply = "已完成操作。"
            
            # 输出思考内容，即使没有工具调用
            # if final_ai_message and reply.strip():
            #     # 检查是否已经输出过这个消息的思考内容
            #     if id(final_ai_message) not in intermediate_ai_ids:
            #         debug_log(f"[run_turn_stream] 发送最终思考: {reply[:100]}...")
            #         yield {
            #             "event": "thought",
            #             "text": reply,
            #         }
            
            debug_log(f"[run_turn_stream] YIELD final reply_len={len(reply)}")
            yield {
                "event": "final",
                "reply": reply,
                "finished": self._is_finish_reply(reply),
                "steps": self._estimate_steps(self.messages),
                "tool_calls": len(getattr(final_ai_message, "tool_calls", []) or []) if final_ai_message else 0,
                "requires_commit": requires_commit,
            }
        except Exception as exc:
            debug_log(f"[run_turn_stream] 异常: {exc}")
            import traceback
            traceback.print_exc()
            yield {
                "event": "error",
                "message": str(exc),
            }
            return

    @staticmethod
    def _last_ai_message(messages: List[BaseMessage]) -> AIMessage:
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                return message
        return AIMessage(content="")

    @staticmethod
    def _last_ai_message_without_tool_calls(messages: List[BaseMessage]) -> Optional[AIMessage]:
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                tool_calls = list(getattr(message, "tool_calls", []) or [])
                if not tool_calls:
                    return message
        return None

    @staticmethod
    def _extract_content(message: AIMessage) -> str:
        if isinstance(message.content, str):
            return message.content
        return str(message.content)

    @staticmethod
    def _extract_tool_content(message: ToolMessage) -> str:
        if isinstance(message.content, str):
            return message.content
        return str(message.content)

    @staticmethod
    def _is_finish_reply(reply: str) -> bool:
        return reply.strip().lower().startswith("finish:")

    @staticmethod
    def _estimate_steps(messages: List[BaseMessage]) -> int:
        return sum(1 for message in messages if isinstance(message, AIMessage))

    # ------------------------------------------------------------------
    # History persistence (serialization / deserialization)
    # ------------------------------------------------------------------

    @staticmethod
    def save_history(messages: List[BaseMessage], path: Path) -> None:
        """Serialize a list of BaseMessage to a JSON file.

        Args:
            messages: The message list to persist.
            path: Target file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [dumpd(msg) for msg in messages]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, default=str)

    @staticmethod
    def load_history(path: Path) -> List[BaseMessage]:
        """Deserialize a list of BaseMessage from a JSON file.

        Args:
            path: Source file path.

        Returns:
            The restored message list, or an empty list if the file does
            not exist or is corrupted.
        """
        if not path.exists():
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return [load(item) for item in data]
        except Exception:
            return []
