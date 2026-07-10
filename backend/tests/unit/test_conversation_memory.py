from types import SimpleNamespace

from app.services.conversation_memory import (
    MAX_MEMORY_CHARS,
    build_conversation_memory,
)


def message(role: str, content: str):
    return SimpleNamespace(role=role, content=content)


def test_build_conversation_memory_keeps_only_the_latest_six_messages() -> None:
    messages = [
        message("user" if index % 2 == 0 else "assistant", f"Message {index}")
        for index in range(8)
    ]

    memory = build_conversation_memory(messages)

    assert "Message 0" not in memory
    assert "Message 1" not in memory
    assert "Message 2" in memory
    assert "Message 7" in memory


def test_build_conversation_memory_truncates_each_message_and_total_output() -> None:
    memory = build_conversation_memory(
        [message("user", "x" * (MAX_MEMORY_CHARS + 100))]
    )

    assert len(memory) <= MAX_MEMORY_CHARS
    assert "[truncated]" in memory
    assert memory.startswith("Conversation context (not code evidence):")
