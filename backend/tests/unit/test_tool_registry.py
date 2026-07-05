import pytest

from app.agent.tool_registry import ToolRegistry
from app.errors import DomainError


def fake_search() -> list[object]:
    return []


def test_registry_registers_and_returns_callable_tools() -> None:
    registry = ToolRegistry()

    registry.register("hybrid_search", fake_search)

    assert registry.get("hybrid_search") is fake_search
    assert registry.names == ("hybrid_search",)


def test_registry_preserves_registration_order() -> None:
    registry = ToolRegistry()

    registry.register("read_entity", fake_search)
    registry.register("graph_search", lambda: [])

    assert registry.names == ("read_entity", "graph_search")


def test_registry_rejects_duplicate_name() -> None:
    registry = ToolRegistry()
    registry.register("hybrid_search", fake_search)

    with pytest.raises(
        ValueError,
        match="tool 'hybrid_search' is already registered",
    ):
        registry.register("hybrid_search", fake_search)


@pytest.mark.parametrize("name", ["", " ", "\r\n"])
def test_registry_rejects_blank_name(name: str) -> None:
    with pytest.raises(ValueError, match="tool name must not be blank"):
        ToolRegistry().register(name, fake_search)


def test_registry_rejects_non_callable_tool() -> None:
    with pytest.raises(TypeError, match="tool must be callable"):
        ToolRegistry().register("hybrid_search", object())


def test_registry_reports_unknown_tool() -> None:
    with pytest.raises(DomainError) as raised:
        ToolRegistry().get("missing")

    assert raised.value.code == "AGENT_TOOL_NOT_FOUND"
    assert raised.value.message == "Agent tool 'missing' is not registered."
    assert raised.value.status_code == 500
