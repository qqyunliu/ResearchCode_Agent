from collections.abc import Callable

from app.errors import DomainError

AgentTool = Callable[..., object]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def register(self, name: str, tool: AgentTool) -> None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("tool name must not be blank")
        if not callable(tool):
            raise TypeError("tool must be callable")
        if normalized_name in self._tools:
            raise ValueError(
                f"tool '{normalized_name}' is already registered"
            )
        self._tools[normalized_name] = tool

    def get(self, name: str) -> AgentTool:
        try:
            return self._tools[name]
        except KeyError as error:
            raise DomainError(
                code="AGENT_TOOL_NOT_FOUND",
                message=f"Agent tool '{name}' is not registered.",
                status_code=500,
            ) from error
