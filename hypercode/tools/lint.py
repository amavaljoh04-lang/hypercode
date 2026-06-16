"""Outil de linting et vérification de code."""

import asyncio
import os
import shutil
from hypercode.tools.base import Tool, ToolResult


class LintTool(Tool):
    name = "lint"
    description = "Vérifie la qualité du code avec des linters (ruff, eslint, pylint, etc.). Détecte automatiquement le langage et le linter approprié."
    parameters = {
        "path": {
            "type": "string",
            "description": "Fichier ou répertoire à vérifier",
            "required": True,
        },
        "linter": {
            "type": "string",
            "description": "Linter spécifique à utiliser (optionnel, auto-détecté sinon). Ex: 'ruff', 'eslint', 'pylint', 'flake8'",
        },
        "fix": {
            "type": "boolean",
            "description": "Corriger automatiquement les erreurs si possible (défaut: false)",
        },
    }

    async def execute(self, path: str, linter: str = None, fix: bool = False, **kwargs) -> ToolResult:
        """Lint le code."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return ToolResult(success=False, output="", error=f"Chemin non trouvé: {path}")

        # Déterminer le linter
        if linter:
            cmd = self._build_command(linter, path, fix)
        else:
            cmd = self._auto_detect(path, fix)

        if not cmd:
            return ToolResult(success=False, output="", error="Aucun linter détecté. Installe ruff, eslint, ou pylint.")

        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        except asyncio.TimeoutError:
            process.kill()
            return ToolResult(success=False, output="", error="Lint timeout (60s)")

        output = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        combined = output
        if err:
            combined = f"{output}\n{err}" if output else err

        if len(combined) > 5000:
            combined = combined[:5000] + "\n[...tronqué]"

        if process.returncode == 0:
            return ToolResult(success=True, output=combined or "Aucune erreur détectée !")
        return ToolResult(success=False, output=combined, error=f"Lint a trouvé des problèmes (code {process.returncode})")

    def _build_command(self, linter: str, path: str, fix: bool) -> str:
        fix_flag = ""
        if linter == "ruff":
            fix_flag = " --fix" if fix else ""
            return f"ruff check{fix_flag} '{path}'"
        elif linter == "eslint":
            fix_flag = " --fix" if fix else ""
            return f"npx eslint{fix_flag} '{path}'"
        elif linter == "pylint":
            return f"pylint '{path}'"
        elif linter == "flake8":
            return f"flake8 '{path}'"
        elif linter == "mypy":
            return f"mypy '{path}'"
        return f"{linter} '{path}'"

    def _auto_detect(self, path: str, fix: bool) -> str | None:
        ext = os.path.splitext(path)[1] if os.path.isfile(path) else ""

        # Python
        if ext == ".py" or (os.path.isdir(path) and any(
            f.endswith(".py") for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))
        )):
            if shutil.which("ruff"):
                return self._build_command("ruff", path, fix)
            if shutil.which("flake8"):
                return self._build_command("flake8", path, fix)
            if shutil.which("pylint"):
                return self._build_command("pylint", path, fix)

        # JavaScript/TypeScript
        if ext in (".js", ".jsx", ".ts", ".tsx") or (os.path.isdir(path) and os.path.exists(os.path.join(path, "package.json"))):
            return self._build_command("eslint", path, fix)

        return None
