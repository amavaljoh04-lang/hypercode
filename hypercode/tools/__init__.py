"""Système d'outils de HyperCode — 20 outils pour un agent surpuissant."""

from hypercode.tools.base import Tool, ToolResult

# Outils de base
from hypercode.tools.bash import BashTool
from hypercode.tools.edit import EditTool
from hypercode.tools.read import ReadTool
from hypercode.tools.write import WriteTool
from hypercode.tools.multiwrite import MultiWriteTool
from hypercode.tools.search import SearchTool
from hypercode.tools.git import GitTool
from hypercode.tools.web import WebTool
from hypercode.tools.todo import TodoTool

# Outils de fichiers
from hypercode.tools.tree import TreeTool
from hypercode.tools.find import FindTool
from hypercode.tools.patch import PatchTool
from hypercode.tools.replace import ReplaceTool
from hypercode.tools.diff import DiffTool
from hypercode.tools.archive import ArchiveTool
from hypercode.tools.download import DownloadTool

# Outils de développement
from hypercode.tools.http import HttpTool
from hypercode.tools.lint import LintTool
from hypercode.tools.test_runner import TestRunnerTool
from hypercode.tools.process import ProcessTool
from hypercode.tools.docker import DockerTool
from hypercode.tools.database import DatabaseTool
from hypercode.tools.env import EnvTool
from hypercode.tools.ssh_tool import SSHTool

# Outils cognitifs
from hypercode.tools.think import ThinkTool
from hypercode.tools.clipboard import ClipboardTool

ALL_TOOLS = [
    # Core (les plus utilisés)
    BashTool(),
    WriteTool(),
    MultiWriteTool(),
    EditTool(),
    ReadTool(),
    SearchTool(),

    # Fichiers & navigation
    TreeTool(),
    FindTool(),
    PatchTool(),
    ReplaceTool(),
    DiffTool(),

    # Réseau & web
    WebTool(),
    HttpTool(),
    DownloadTool(),

    # Développement
    GitTool(),
    LintTool(),
    TestRunnerTool(),

    # Infrastructure
    ProcessTool(),
    DockerTool(),
    DatabaseTool(),
    EnvTool(),
    SSHTool(),
    ArchiveTool(),

    # Cognitif
    TodoTool(),
    ThinkTool(),
    ClipboardTool(),
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
