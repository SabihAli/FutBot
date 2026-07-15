class ToolError(Exception):
    """Base class for tool failures."""


class ToolNotFoundError(ToolError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Tool not found: {name}")
        self.name = name


class ToolExecutionError(ToolError):
    pass
