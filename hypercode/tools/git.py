"""Outil Git pour HyperCode."""

import asyncio
import os
from hypercode.tools.base import Tool, ToolResult


class GitTool(Tool):
    name = "git"
    description = "Exécute des opérations Git (status, add, commit, push, pull, diff, log, branch, etc.)."
    parameters = {
        "command": {
            "type": "string",
            "description": "La commande git à exécuter (sans le préfixe 'git'). Ex: 'status', 'add .', 'commit -m \"msg\"'",
            "required": True,
        },
        "working_dir": {
            "type": "string",
            "description": "Répertoire du repo git (optionnel)",
        },
    }

    async def execute(self, command: str, working_dir: str = None, **kwargs) -> ToolResult:
        """Exécute une commande git."""
        cwd = working_dir or os.getcwd()

        # Sécurité: bloquer les commandes destructives
        dangerous = ["push --force", "reset --hard", "clean -fd"]
        for d in dangerous:
            if d in command and "--force-with-lease" not in command:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Commande dangereuse bloquée: git {command}. Utilise --force-with-lease si nécessaire.",
                )

        try:
            process = await asyncio.create_subprocess_shell(
                f"git {command}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=60
            )

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            output = stdout_str
            if stderr_str and process.returncode == 0:
                output = f"{stdout_str}\n{stderr_str}" if stdout_str else stderr_str

            if len(output) > 5000:
                output = output[:5000] + "\n[...tronqué]"

            return ToolResult(
                success=process.returncode == 0,
                output=output,
                error=stderr_str if process.returncode != 0 else None,
            )

        except asyncio.TimeoutError:
            return ToolResult(success=False, output="", error="Git timeout (60s)")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
