"""Outil d'édition de fichiers."""

import os
from hypercode.tools.base import Tool, ToolResult


class EditTool(Tool):
    name = "edit"
    description = "Remplace du texte dans un fichier existant. Le old_text doit être unique dans le fichier."
    parameters = {
        "file_path": {
            "type": "string",
            "description": "Chemin absolu du fichier à modifier",
            "required": True,
        },
        "old_text": {
            "type": "string",
            "description": "Le texte exact à remplacer (doit être unique dans le fichier)",
            "required": True,
        },
        "new_text": {
            "type": "string",
            "description": "Le nouveau texte qui remplacera l'ancien",
            "required": True,
        },
    }

    async def execute(self, file_path: str, old_text: str, new_text: str, **kwargs) -> ToolResult:
        """Remplace du texte dans un fichier."""
        try:
            file_path = os.path.expanduser(file_path)

            if not os.path.exists(file_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Fichier non trouvé: {file_path}",
                )

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            count = content.count(old_text)
            if count == 0:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Texte non trouvé dans {file_path}",
                )
            if count > 1:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Texte trouvé {count} fois dans {file_path} (doit être unique)",
                )

            new_content = content.replace(old_text, new_text, 1)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(
                success=True,
                output=f"Fichier modifié: {file_path}",
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
