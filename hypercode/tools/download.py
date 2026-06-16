"""Outil de téléchargement de fichiers."""

import os
import httpx
from hypercode.tools.base import Tool, ToolResult


class DownloadTool(Tool):
    name = "download"
    description = "Télécharge un fichier depuis une URL. Utile pour récupérer des assets, des librairies, des dépendances."
    parameters = {
        "url": {
            "type": "string",
            "description": "URL du fichier à télécharger",
            "required": True,
        },
        "output": {
            "type": "string",
            "description": "Chemin de destination du fichier téléchargé",
            "required": True,
        },
    }

    async def execute(self, url: str, output: str, **kwargs) -> ToolResult:
        """Télécharge un fichier."""
        output = os.path.expanduser(output)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                resp = await client.get(url)

                if resp.status_code != 200:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"HTTP {resp.status_code} pour {url}",
                    )

                with open(output, "wb") as f:
                    f.write(resp.content)

                size = os.path.getsize(output)
                return ToolResult(
                    success=True,
                    output=f"Téléchargé: {url}\n→ {output} ({size} bytes)",
                )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Erreur de téléchargement: {e}")
