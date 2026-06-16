"""Outil d'archivage (zip, tar, extraction)."""

import asyncio
import os
from hypercode.tools.base import Tool, ToolResult


class ArchiveTool(Tool):
    name = "archive"
    description = "Crée ou extrait des archives (zip, tar.gz). Utile pour packager un projet ou extraire des dépendances."
    parameters = {
        "action": {
            "type": "string",
            "description": "'create' pour créer une archive, 'extract' pour extraire",
            "required": True,
            "enum": ["create", "extract"],
        },
        "path": {
            "type": "string",
            "description": "Fichier archive (pour extract) ou dossier source (pour create)",
            "required": True,
        },
        "output": {
            "type": "string",
            "description": "Destination: nom de l'archive (pour create) ou dossier d'extraction (pour extract)",
        },
        "format": {
            "type": "string",
            "description": "Format: 'zip', 'tar.gz', 'tar' (défaut: auto-détecté)",
        },
    }

    async def execute(self, action: str, path: str, output: str = None,
                      format: str = None, **kwargs) -> ToolResult:
        """Crée ou extrait une archive."""
        path = os.path.expanduser(path)

        if action == "create":
            return await self._create(path, output, format)
        elif action == "extract":
            return await self._extract(path, output)
        return ToolResult(success=False, output="", error=f"Action inconnue: {action}")

    async def _create(self, source: str, output: str = None, fmt: str = None) -> ToolResult:
        if not os.path.exists(source):
            return ToolResult(success=False, output="", error=f"Source non trouvée: {source}")

        name = os.path.basename(source.rstrip("/"))
        if fmt == "zip" or (output and output.endswith(".zip")):
            out = output or f"{name}.zip"
            cmd = f"cd '{os.path.dirname(source)}' && zip -r '{os.path.abspath(out)}' '{name}'"
        else:
            out = output or f"{name}.tar.gz"
            cmd = f"tar -czf '{out}' -C '{os.path.dirname(source)}' '{name}'"

        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode == 0:
            size = os.path.getsize(out) if os.path.exists(out) else 0
            return ToolResult(success=True, output=f"Archive créée: {out} ({size} bytes)")
        return ToolResult(success=False, output="", error=stderr.decode())

    async def _extract(self, archive: str, output: str = None) -> ToolResult:
        if not os.path.exists(archive):
            return ToolResult(success=False, output="", error=f"Archive non trouvée: {archive}")

        dest = output or "."
        os.makedirs(dest, exist_ok=True)

        if archive.endswith(".zip"):
            cmd = f"unzip -o '{archive}' -d '{dest}'"
        elif archive.endswith((".tar.gz", ".tgz")):
            cmd = f"tar -xzf '{archive}' -C '{dest}'"
        elif archive.endswith(".tar"):
            cmd = f"tar -xf '{archive}' -C '{dest}'"
        else:
            cmd = f"tar -xf '{archive}' -C '{dest}'"

        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            return ToolResult(success=True, output=f"Archive extraite dans: {dest}")
        return ToolResult(success=False, output="", error=stderr.decode())
