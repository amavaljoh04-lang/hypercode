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

    async def execute(self, files=None, **kwargs) -> ToolResult:
        """Crée plusieurs fichiers."""
        if not files or not isinstance(files, list):
            return ToolResult(
                success=False,
                output="",
                error="Paramètre 'files' requis : une liste de {\"path\": \"...\", \"content\": \"...\"}",
            )

        created = []
        errors = []

        for file_info in files:
            if isinstance(file_info, dict):
                path = file_info.get("path", "") or file_info.get("file_path", "")
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

        if not created and not errors:
            return ToolResult(success=False, output="", error="La liste 'files' est vide")

        return ToolResult(
            success=len(errors) == 0,
            output="\n".join(output_parts),
            error="\n".join(errors) if errors else None,
        )
