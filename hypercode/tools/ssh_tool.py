"""Outil SSH pour la gestion de serveurs distants."""

import asyncio
from hypercode.tools.base import Tool, ToolResult


class SSHTool(Tool):
    name = "ssh"
    description = "Exécute des commandes sur un serveur distant via SSH. Utile pour le déploiement et l'administration."
    parameters = {
        "host": {
            "type": "string",
            "description": "Adresse du serveur (ex: user@host ou host)",
            "required": True,
        },
        "command": {
            "type": "string",
            "description": "Commande à exécuter sur le serveur",
            "required": True,
        },
        "port": {
            "type": "integer",
            "description": "Port SSH (défaut: 22)",
        },
        "key": {
            "type": "string",
            "description": "Chemin de la clé SSH (optionnel)",
        },
    }

    async def execute(self, host: str, command: str, port: int = 22,
                      key: str = None, **kwargs) -> ToolResult:
        """Exécute une commande SSH."""
        ssh_cmd = f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {port}"
        if key:
            ssh_cmd += f" -i '{key}'"
        ssh_cmd += f" {host} '{command}'"

        try:
            process = await asyncio.create_subprocess_shell(
                ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

            output = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()

            if len(output) > 5000:
                output = output[:5000] + "\n[...tronqué]"

            if process.returncode == 0:
                return ToolResult(success=True, output=output)
            return ToolResult(success=False, output=output, error=err)

        except asyncio.TimeoutError:
            return ToolResult(success=False, output="", error="SSH timeout (60s)")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
