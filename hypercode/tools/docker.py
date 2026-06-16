"""Outil Docker pour la gestion de conteneurs."""

import asyncio
from hypercode.tools.base import Tool, ToolResult


class DockerTool(Tool):
    name = "docker"
    description = "Gère les conteneurs Docker: build, run, stop, logs, ps, exec. Utile pour déployer et tester des applications."
    parameters = {
        "command": {
            "type": "string",
            "description": "Commande docker (sans le préfixe 'docker'). Ex: 'ps', 'build -t app .', 'run -d -p 8080:80 app', 'logs container_name', 'compose up -d'",
            "required": True,
        },
        "working_dir": {
            "type": "string",
            "description": "Répertoire de travail (optionnel)",
        },
    }

    async def execute(self, command: str, working_dir: str = None, **kwargs) -> ToolResult:
        """Exécute une commande docker."""
        import os
        cwd = working_dir or os.getcwd()

        # Sécurité: pas de rm -f sur des images système
        dangerous = ["system prune -a --force", "rmi $("]
        for d in dangerous:
            if d in command:
                return ToolResult(success=False, output="", error=f"Commande potentiellement dangereuse bloquée: docker {command}")

        process = await asyncio.create_subprocess_shell(
            f"docker {command}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        except asyncio.TimeoutError:
            process.kill()
            return ToolResult(success=False, output="", error="Docker timeout (120s)")

        output = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        if len(output) > 5000:
            output = output[:5000] + "\n[...tronqué]"

        if process.returncode == 0:
            combined = output
            if err:
                combined += f"\n{err}"
            return ToolResult(success=True, output=combined)

        return ToolResult(success=False, output=output, error=err)
