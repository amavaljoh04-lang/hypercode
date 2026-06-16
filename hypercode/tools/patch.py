"""Outil de remplacement multi-occurrences dans un fichier."""

import os
import re
from hypercode.tools.base import Tool, ToolResult


class PatchTool(Tool):
    name = "patch"
    description = "Remplace TOUTES les occurrences d'un texte dans un fichier, ou insère du texte à une ligne spécifique. Plus puissant que edit pour les modifications multiples."
    parameters = {
        "file_path": {
            "type": "string",
            "description": "Chemin du fichier à modifier",
            "required": True,
        },
        "action": {
            "type": "string",
            "description": "'replace_all' pour remplacer toutes les occurrences, 'insert_at' pour insérer à une ligne, 'delete_lines' pour supprimer des lignes",
            "required": True,
            "enum": ["replace_all", "insert_at", "delete_lines"],
        },
        "old_text": {
            "type": "string",
            "description": "Texte à remplacer (pour replace_all)",
        },
        "new_text": {
            "type": "string",
            "description": "Nouveau texte (pour replace_all et insert_at)",
        },
        "line": {
            "type": "integer",
            "description": "Numéro de ligne (pour insert_at et delete_lines)",
        },
        "end_line": {
            "type": "integer",
            "description": "Ligne de fin pour delete_lines (incluse)",
        },
    }

    async def execute(self, file_path: str, action: str, old_text: str = None, new_text: str = None,
                      line: int = None, end_line: int = None, **kwargs) -> ToolResult:
        """Modifie un fichier."""
        file_path = os.path.expanduser(file_path)

        if not os.path.exists(file_path):
            return ToolResult(success=False, output="", error=f"Fichier non trouvé: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if action == "replace_all":
                if not old_text:
                    return ToolResult(success=False, output="", error="old_text requis pour replace_all")
                count = content.count(old_text)
                if count == 0:
                    return ToolResult(success=False, output="", error="Texte non trouvé")
                content = content.replace(old_text, new_text or "")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return ToolResult(success=True, output=f"{count} remplacement(s) dans {file_path}")

            elif action == "insert_at":
                if line is None or new_text is None:
                    return ToolResult(success=False, output="", error="line et new_text requis pour insert_at")
                lines = content.split("\n")
                idx = max(0, min(line - 1, len(lines)))
                lines.insert(idx, new_text)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                return ToolResult(success=True, output=f"Texte inséré à la ligne {line} dans {file_path}")

            elif action == "delete_lines":
                if line is None:
                    return ToolResult(success=False, output="", error="line requis pour delete_lines")
                lines = content.split("\n")
                end = end_line or line
                start_idx = max(0, line - 1)
                end_idx = min(len(lines), end)
                deleted = lines[start_idx:end_idx]
                del lines[start_idx:end_idx]
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                return ToolResult(success=True, output=f"{len(deleted)} ligne(s) supprimée(s) dans {file_path}")

            else:
                return ToolResult(success=False, output="", error=f"Action inconnue: {action}")

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
