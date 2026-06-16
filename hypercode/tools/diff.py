"""Outil de diff entre fichiers ou versions."""

import asyncio
import os
from hypercode.tools.base import Tool, ToolResult


class DiffTool(Tool):
    name = "diff"
    description = "Compare deux fichiers ou montre les modifications git d'un fichier. Utile pour vérifier les changements."
    parameters = {
        "action": {
            "type": "string",
            "description": "'files' pour comparer 2 fichiers, 'git' pour voir les modifications git",
            "required": True,
            "enum": ["files", "git"],
        },
        "file_a": {
            "type": "string",
            "description": "Premier fichier (pour files) ou fichier à diff (pour git)",
            "required": True,
        },
        "file_b": {
            "type": "string",
            "description": "Deuxième fichier (pour files uniquement)",
        },
    }

    async def execute(self, action: str, file_a: str, file_b: str = None, **kwargs) -> ToolResult:
        """Exécute un diff."""
        file_a = os.path.expanduser(file_a)

        if action == "files":
            if not file_b:
                return ToolResult(success=False, output="", error="file_b requis pour comparer deux fichiers")
            file_b = os.path.expanduser(file_b)
            cmd = f"diff -u '{file_a}' '{file_b}'"
        elif action == "git":
            cmd = f"git diff -- '{file_a}'"
        else:
            return ToolResult(success=False, output="", error=f"Action inconnue: {action}")

        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode("utf-8", errors="replace").strip()

        if not output:
            return ToolResult(success=True, output="Aucune différence trouvée.")

        if len(output) > 5000:
            output = output[:5000] + "\n[...tronqué]"

        return ToolResult(success=True, output=output)
