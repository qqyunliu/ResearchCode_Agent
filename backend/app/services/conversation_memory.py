from collections.abc import Sequence
from typing import Protocol


MAX_MEMORY_MESSAGES = 6
MAX_MESSAGE_CHARS = 600
MAX_MEMORY_CHARS = 4_000
TRUNCATION_MARKER = " [truncated]"


class ConversationMessage(Protocol):
    role: str
    content: str


def build_conversation_memory(
    messages: Sequence[ConversationMessage],
) -> str:
    """Render a bounded recent window for conversational continuity."""
    recent_messages = messages[-MAX_MEMORY_MESSAGES:]
    lines = ["Conversation context (not code evidence):"]
    for message in recent_messages:
        content = _truncate(message.content.strip(), MAX_MESSAGE_CHARS)
        lines.append(f"{message.role.title()}: {content}")
    return _truncate("\n".join(lines), MAX_MEMORY_CHARS)


def augment_question_with_memory(
    question: str,
    conversation_memory: str,
) -> str:
    if not conversation_memory:
        return question
    return f"{conversation_memory}\n\nCurrent question:\n{question}"


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER
