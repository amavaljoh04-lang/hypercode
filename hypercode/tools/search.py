"""Outil de recherche dans le code (grep/ripgrep)."""

import asyncio
import os
import shutil
from hypercode.tools.base import Tool, ToolResult


class SearchTool(Tool):
    name = "search"
    description = "Recherche un pattern (regex) dans les fichiers du projet. Utilise ripgrep si disponible."
    parameters = {
        "pattern": {
            "type": "string",
            "description": "Pattern regex à rechercher",
            "required": True,
        },
        "path": {
            "type": "string",
            "description": "Répertoire ou fichier où chercher (défaut: répertoire courant)",
        },
        "file_pattern": {
            "type": "string",
            "description": "Glob pattern pour filtrer les fichiers (ex: '*.py', '*.js')",
        },
        "case_insensitive": {
            "type": "boolean",
            "description": "Recherche insensible à la casse (défaut: false)",
        },
        "max_results": {
            "type": "integer",
            "description": "Nombre max de résultats (défaut: 50)",
        },
    }

    async def execute(
        self,
        pattern: str,
        path: str = None,
        file_pattern: str = None,
        case_insensitive: bool = False,
        max_results: int = 50,
        **kwargs,
    ) -> ToolResult:
        """Recherche dans les fichiers."""
        search_path = path or os.getcwd()
        search_path = os.path.expanduser(search_path)

        # Utiliser ripgrep si disponible, sinon grep
        rg = shutil.which("rg")
        if rg:
            cmd = [rg, "--no-heading", "--line-number", "--color=never"]
            if case_insensitive:
                cmd.append("-i")
            if file_pattern:
                cmd.extend(["-g", file_pattern])
            cmd.extend(["-m", str(max_results), pattern, search_path])
        else:
            cmd = ["grep", "-rn", "--color=never"]
            if case_insensitive:
                cmd.append("-i")
            if file_pattern:
                cmd.extend(["--include", file_pattern])
            cmd.extend(["-m", str(max_results), pattern, search_path])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=30
            )

            output = stdout.decode("utf-8", errors="replace").strip()

            if not output:
                return ToolResult(
                    success=True,
                    output="Aucun résultat trouvé.",
                )

            lines = output.split("\n")
            if len(lines) > max_results:
                lines = lines[:max_results]
                output = "\n".join(lines) + f"\n[...{max_results} résultats max]"

            return ToolResult(success=True, output=output)

        except asyncio.TimeoutError:
            return ToolResult(success=False, output="", error="Recherche timeout (30s)")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
