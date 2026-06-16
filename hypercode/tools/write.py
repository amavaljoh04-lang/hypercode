"""Outil d'écriture de fichiers."""

import os
from hypercode.tools.base import Tool, ToolResult


class WriteTool(Tool):
    name = "write"
    description = "Écrit du contenu dans un fichier (crée le fichier et les dossiers parents si nécessaire)."
    parameters = {
        "file_path": {
            "type": "string",
            "description": "Chemin absolu du fichier à écrire",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "Le contenu complet à écrire dans le fichier",
            "required": True,
        },
    }

    async def execute(self, file_path: str, content: str, **kwargs) -> ToolResult:
        """Écrit un fichier."""
        try:
            file_path = os.path.expanduser(file_path)

            # Créer les dossiers parents
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            lines = content.count("\n") + 1
            return ToolResult(
                success=True,
                output=f"Fichier écrit: {file_path} ({lines} lignes)",
            )

        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission refusée: {file_path}. Essaie avec sudo.",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
