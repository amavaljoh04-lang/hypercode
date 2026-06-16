"""Outil d'écriture de plusieurs fichiers en une seule opération."""

import os
from hypercode.tools.base import Tool, ToolResult


class MultiWriteTool(Tool):
    name = "multiwrite"
    description = "Crée plusieurs fichiers en une seule opération. Beaucoup plus efficace que write pour créer un projet complet."
    parameters = {
        "files": {
            "type": "array",
            "description": "Liste de fichiers à créer. Chaque élément: {\"path\": \"/chemin/fichier\", \"content\": \"contenu\"}",
            "required": True,
        },
    }

    async def execute(self, files: list, **kwargs) -> ToolResult:
        """Crée plusieurs fichiers."""
        created = []
        errors = []

        for file_info in files:
            if isinstance(file_info, dict):
                path = file_info.get("path", "")
                content = file_info.get("content", "")
            else:
                errors.append(f"Format invalide: {file_info}")
                continue

            if not path:
                errors.append("Chemin vide ignoré")
                continue

            path = os.path.expanduser(path)

            try:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                lines = content.count("\n") + 1
                created.append(f"  ✓ {path} ({lines} lignes)")
            except Exception as e:
                errors.append(f"  ✗ {path}: {e}")

        output_parts = []
        if created:
            output_parts.append(f"Fichiers créés ({len(created)}):\n" + "\n".join(created))
        if errors:
            output_parts.append(f"Erreurs ({len(errors)}):\n" + "\n".join(errors))

        return ToolResult(
            success=len(errors) == 0,
            output="\n".join(output_parts),
            error="\n".join(errors) if errors else None,
        )
