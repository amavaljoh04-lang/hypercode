"""Outil de recherche de fichiers par nom."""

import asyncio
import os
import fnmatch
from hypercode.tools.base import Tool, ToolResult


class FindTool(Tool):
    name = "find"
    description = "Trouve des fichiers par nom ou pattern glob dans un répertoire. Utile pour localiser des fichiers dans un projet."
    parameters = {
        "pattern": {
            "type": "string",
            "description": "Pattern glob pour le nom de fichier (ex: '*.py', 'config.*', 'Dockerfile')",
            "required": True,
        },
        "path": {
            "type": "string",
            "description": "Répertoire de recherche (défaut: répertoire courant)",
        },
        "max_results": {
            "type": "integer",
            "description": "Nombre max de résultats (défaut: 50)",
        },
    }

    async def execute(self, pattern: str, path: str = None, max_results: int = 50, **kwargs) -> ToolResult:
        """Trouve des fichiers."""
        search_path = os.path.expanduser(path or os.getcwd())
        if not os.path.isdir(search_path):
            return ToolResult(success=False, output="", error=f"Répertoire non trouvé: {search_path}")

        skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv", ".tox", "dist", "build", ".next", ".cache"}
        results = []

        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for filename in files:
                if fnmatch.fnmatch(filename, pattern):
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, search_path)
                    size = os.path.getsize(full_path)
                    results.append(f"{rel_path} ({_format_size(size)})")

                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break

        if not results:
            return ToolResult(success=True, output=f"Aucun fichier trouvé pour '{pattern}' dans {search_path}")

        return ToolResult(success=True, output=f"Fichiers trouvés ({len(results)}):\n" + "\n".join(results))


def _format_size(size: int) -> str:
    if size >= 1_000_000:
        return f"{size/1_000_000:.1f}M"
    elif size >= 1_000:
        return f"{size/1_000:.1f}K"
    return f"{size}B"
