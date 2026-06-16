"""Outil de lecture de fichiers."""

import os
from hypercode.tools.base import Tool, ToolResult


class ReadTool(Tool):
    name = "read"
    description = "Lit le contenu d'un fichier. Supporte les offsets pour les gros fichiers."
    parameters = {
        "file_path": {
            "type": "string",
            "description": "Chemin absolu du fichier à lire",
            "required": True,
        },
        "offset": {
            "type": "integer",
            "description": "Numéro de ligne de départ (1-based, optionnel)",
        },
        "limit": {
            "type": "integer",
            "description": "Nombre de lignes à lire (optionnel, défaut: toutes)",
        },
    }

    async def execute(self, file_path: str, offset: int = None, limit: int = None, **kwargs) -> ToolResult:
        """Lit un fichier."""
        try:
            file_path = os.path.expanduser(file_path)

            if not os.path.exists(file_path):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Fichier non trouvé: {file_path}",
                )

            if os.path.isdir(file_path):
                entries = sorted(os.listdir(file_path))
                listing = "\n".join(entries[:100])
                if len(entries) > 100:
                    listing += f"\n[...{len(entries)} entrées au total]"
                return ToolResult(success=True, output=listing)

            file_size = os.path.getsize(file_path)
            if file_size > 5_000_000:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Fichier trop gros ({file_size} bytes). Utilise offset/limit.",
                )

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = (offset - 1) if offset and offset > 0 else 0
            end = (start + limit) if limit else total_lines

            selected = lines[start:end]
            numbered = ""
            for i, line in enumerate(selected, start=start + 1):
                numbered += f"{i:4d} | {line}"

            if len(numbered) > 10000:
                numbered = numbered[:10000] + f"\n\n[...tronqué, {total_lines} lignes au total]"

            header = f"[{file_path}] ({total_lines} lignes)\n"
            return ToolResult(success=True, output=header + numbered)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
