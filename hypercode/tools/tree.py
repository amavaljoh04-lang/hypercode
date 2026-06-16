"""Outil d'arborescence de fichiers."""

import asyncio
import os
from hypercode.tools.base import Tool, ToolResult


class TreeTool(Tool):
    name = "tree"
    description = "Affiche l'arborescence d'un répertoire. Utile pour comprendre la structure d'un projet."
    parameters = {
        "path": {
            "type": "string",
            "description": "Chemin du répertoire à explorer (défaut: répertoire courant)",
            "required": True,
        },
        "max_depth": {
            "type": "integer",
            "description": "Profondeur max (défaut: 3)",
        },
        "show_hidden": {
            "type": "boolean",
            "description": "Afficher les fichiers cachés (défaut: false)",
        },
    }

    async def execute(self, path: str = ".", max_depth: int = 3, show_hidden: bool = False, **kwargs) -> ToolResult:
        """Affiche l'arborescence."""
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            return ToolResult(success=False, output="", error=f"Pas un répertoire: {path}")

        lines = []
        file_count = 0
        dir_count = 0

        def _walk(current_path: str, prefix: str, depth: int):
            nonlocal file_count, dir_count
            if depth > max_depth:
                return

            try:
                entries = sorted(os.listdir(current_path))
            except PermissionError:
                lines.append(f"{prefix}[permission refusée]")
                return

            if not show_hidden:
                entries = [e for e in entries if not e.startswith(".")]

            # Filtrer les dossiers courants (node_modules, __pycache__, .git, etc.)
            skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv", ".tox", "dist", "build", ".next"}
            entries = [e for e in entries if e not in skip_dirs or show_hidden]

            for i, entry in enumerate(entries):
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                full_path = os.path.join(current_path, entry)

                if os.path.isdir(full_path):
                    dir_count += 1
                    lines.append(f"{prefix}{connector}{entry}/")
                    extension = "    " if is_last else "│   "
                    _walk(full_path, prefix + extension, depth + 1)
                else:
                    file_count += 1
                    size = os.path.getsize(full_path)
                    size_str = _format_size(size)
                    lines.append(f"{prefix}{connector}{entry} ({size_str})")

                if len(lines) > 200:
                    lines.append(f"{prefix}... [tronqué, trop de fichiers]")
                    return

        _walk(path, "", 0)
        summary = f"\n{dir_count} répertoires, {file_count} fichiers"
        return ToolResult(success=True, output=f"{path}/\n" + "\n".join(lines) + summary)


def _format_size(size: int) -> str:
    if size >= 1_000_000:
        return f"{size/1_000_000:.1f}M"
    elif size >= 1_000:
        return f"{size/1_000:.1f}K"
    return f"{size}B"
