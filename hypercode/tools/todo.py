"""Outil de gestion des tâches (TodoWrite)."""

from hypercode.tools.base import Tool, ToolResult


# État global des todos pour la session
_session_todos: list[dict] = []


class TodoTool(Tool):
    name = "todo"
    description = "Gère une liste de tâches pour tracker l'avancement. Actions: add, complete, list, update."
    parameters = {
        "action": {
            "type": "string",
            "description": "'add' pour ajouter, 'complete' pour terminer, 'list' pour afficher, 'update' pour modifier le status",
            "required": True,
            "enum": ["add", "complete", "list", "update"],
        },
        "task": {
            "type": "string",
            "description": "Description de la tâche (pour add/complete/update)",
        },
        "status": {
            "type": "string",
            "description": "Status: 'pending', 'in_progress', 'completed' (pour update)",
            "enum": ["pending", "in_progress", "completed"],
        },
        "index": {
            "type": "integer",
            "description": "Index de la tâche à modifier (pour complete/update, 1-based)",
        },
    }

    async def execute(self, action: str, task: str = None, status: str = None, index: int = None, **kwargs) -> ToolResult:
        """Gère les todos."""
        global _session_todos

        if action == "add":
            if not task:
                return ToolResult(success=False, output="", error="Paramètre 'task' requis pour add")
            _session_todos.append({"task": task, "status": "pending"})
            return ToolResult(success=True, output=f"Tâche ajoutée: {task}")

        elif action == "complete":
            idx = (index or len(_session_todos)) - 1
            if 0 <= idx < len(_session_todos):
                _session_todos[idx]["status"] = "completed"
                return ToolResult(success=True, output=f"Tâche terminée: {_session_todos[idx]['task']}")
            return ToolResult(success=False, output="", error="Index invalide")

        elif action == "update":
            idx = (index or 1) - 1
            if 0 <= idx < len(_session_todos):
                if status:
                    _session_todos[idx]["status"] = status
                if task:
                    _session_todos[idx]["task"] = task
                return ToolResult(success=True, output=f"Tâche mise à jour: {_session_todos[idx]['task']} [{_session_todos[idx]['status']}]")
            return ToolResult(success=False, output="", error="Index invalide")

        elif action == "list":
            if not _session_todos:
                return ToolResult(success=True, output="Aucune tâche en cours.")

            icons = {"pending": "[ ]", "in_progress": "[•]", "completed": "[✓]"}
            lines = []
            for i, t in enumerate(_session_todos, 1):
                icon = icons.get(t["status"], "[ ]")
                lines.append(f"{i}. {icon} {t['task']}")

            return ToolResult(success=True, output="# Todos\n" + "\n".join(lines))

        return ToolResult(success=False, output="", error=f"Action inconnue: {action}")


def get_todos() -> list[dict]:
    """Retourne les todos de la session."""
    return _session_todos.copy()


def reset_todos():
    """Reset les todos."""
    global _session_todos
    _session_todos = []
