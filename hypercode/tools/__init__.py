"""Système d'outils de HyperCode."""

from hypercode.tools.base import Tool, ToolResult
from hypercode.tools.bash import BashTool
from hypercode.tools.edit import EditTool
from hypercode.tools.read import ReadTool
from hypercode.tools.write import WriteTool
from hypercode.tools.search import SearchTool
from hypercode.tools.git import GitTool
from hypercode.tools.web import WebTool
from hypercode.tools.todo import TodoTool

ALL_TOOLS = [
    BashTool(),
    EditTool(),
    ReadTool(),
    WriteTool(),
    SearchTool(),
    GitTool(),
    WebTool(),
    TodoTool(),
]


def get_tools_schema() -> list[dict]:
    """Retourne le schéma JSON de tous les outils pour le LLM."""
    return [tool.to_schema() for tool in ALL_TOOLS]


def get_tool_by_name(name: str) -> Tool | None:
    """Récupère un outil par son nom."""
    for tool in ALL_TOOLS:
        if tool.name == name:
            return tool
    return None
