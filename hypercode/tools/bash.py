"""Outil d'exécution de commandes shell."""

import asyncio
import os
from hypercode.tools.base import Tool, ToolResult


class BashTool(Tool):
    name = "bash"
    description = "Execute une commande shell. Utilise sudo si des permissions élevées sont nécessaires."
    parameters = {
        "command": {
            "type": "string",
            "description": "La commande shell à exécuter",
            "required": True,
        },
        "working_dir": {
            "type": "string",
            "description": "Répertoire de travail (optionnel, utilise le répertoire courant par défaut)",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout en secondes (défaut: 120)",
        },
    }

    async def execute(self, command: str, working_dir: str = None, timeout: int = 120, **kwargs) -> ToolResult:
        """Exécute une commande shell."""
        cwd = working_dir or os.getcwd()

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ, "TERM": "dumb", "NO_COLOR": "1"},
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Commande timeout après {timeout}s: {command}",
                )

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            # Tronquer si trop long
            max_len = 8000
            if len(stdout_str) > max_len:
                stdout_str = stdout_str[:max_len] + f"\n\n[...tronqué, {len(stdout_str)} caractères au total]"

            output = stdout_str
            if stderr_str and process.returncode != 0:
                output = f"{stdout_str}\n{stderr_str}" if stdout_str else stderr_str

            return ToolResult(
                success=process.returncode == 0,
                output=output,
                error=stderr_str if process.returncode != 0 else None,
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
