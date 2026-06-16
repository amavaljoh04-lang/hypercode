"""Outil de gestion de processus."""

import asyncio
import os
import signal
from hypercode.tools.base import Tool, ToolResult


class ProcessTool(Tool):
    name = "process"
    description = "Gère les processus système: lister, tuer, lancer en arrière-plan. Utile pour gérer des serveurs et des processus longs."
    parameters = {
        "action": {
            "type": "string",
            "description": "'list' pour lister, 'kill' pour tuer, 'background' pour lancer en background",
            "required": True,
            "enum": ["list", "kill", "background"],
        },
        "pid": {
            "type": "integer",
            "description": "PID du processus à tuer (pour kill)",
        },
        "command": {
            "type": "string",
            "description": "Commande à lancer en arrière-plan (pour background)",
        },
        "filter": {
            "type": "string",
            "description": "Filtre pour lister les processus (ex: 'python', 'node')",
        },
    }

    async def execute(self, action: str, pid: int = None, command: str = None,
                      filter: str = None, **kwargs) -> ToolResult:
        """Gère les processus."""
        if action == "list":
            return await self._list_processes(filter)
        elif action == "kill":
            return await self._kill_process(pid)
        elif action == "background":
            return await self._run_background(command)
        else:
            return ToolResult(success=False, output="", error=f"Action inconnue: {action}")

    async def _list_processes(self, proc_filter: str = None) -> ToolResult:
        cmd = "ps aux --sort=-%mem"
        if proc_filter:
            cmd += f" | head -1; ps aux | grep -i '{proc_filter}' | grep -v grep"

        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        output = stdout.decode("utf-8", errors="replace").strip()

        if len(output) > 3000:
            output = output[:3000] + "\n[...tronqué]"

        return ToolResult(success=True, output=output)

    async def _kill_process(self, pid: int = None) -> ToolResult:
        if pid is None:
            return ToolResult(success=False, output="", error="PID requis pour kill")

        try:
            os.kill(pid, signal.SIGTERM)
            return ToolResult(success=True, output=f"Signal SIGTERM envoyé au processus {pid}")
        except ProcessLookupError:
            return ToolResult(success=False, output="", error=f"Processus {pid} non trouvé")
        except PermissionError:
            # Essayer avec sudo
            process = await asyncio.create_subprocess_shell(
                f"sudo kill {pid}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode == 0:
                return ToolResult(success=True, output=f"Processus {pid} tué (sudo)")
            return ToolResult(success=False, output="", error=f"Permission refusée pour {pid}")

    async def _run_background(self, command: str = None) -> ToolResult:
        if not command:
            return ToolResult(success=False, output="", error="Commande requise pour background")

        log_file = f"/tmp/hypercode_bg_{os.getpid()}.log"

        process = await asyncio.create_subprocess_shell(
            f"nohup {command} > {log_file} 2>&1 &",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        # Attendre un peu que le processus démarre
        await asyncio.sleep(2)

        # Récupérer le PID
        pid_proc = await asyncio.create_subprocess_shell(
            f"pgrep -f '{command[:30]}'",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await pid_proc.communicate()
        pids = stdout.decode().strip()

        # Vérifier si le processus tourne
        if not pids:
            # Lire le log pour voir l'erreur
            try:
                with open(log_file, "r") as f:
                    log_content = f.read()[:500]
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Le processus n'a pas démarré.\nLog:\n{log_content}",
                )
            except FileNotFoundError:
                return ToolResult(
                    success=False,
                    output="",
                    error="Le processus n'a pas démarré (pas de log trouvé)",
                )

        return ToolResult(
            success=True,
            output=f"Commande lancée en arrière-plan: {command}\nPID(s): {pids}\nLog: {log_file}",
        )
