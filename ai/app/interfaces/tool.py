from abc import ABC, abstractmethod


class ToolInterface(ABC):
    """Interface for tool execution."""

    @abstractmethod
    async def execute(self, name: str, args: dict) -> str:
        ...

    @abstractmethod
    async def list_tools(self) -> list[dict]:
        ...


class MockTool(ToolInterface):
    """Mock tool provider for testing."""

    async def execute(self, name: str, args: dict) -> str:
        return f"[mock] {name} executed with {args}"

    async def list_tools(self) -> list[dict]:
        return [{"name": "mock_tool", "description": "A mock tool for testing"}]
