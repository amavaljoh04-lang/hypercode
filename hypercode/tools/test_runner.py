"""Outil d'exécution de tests."""

import asyncio
import os
from hypercode.tools.base import Tool, ToolResult


class TestRunnerTool(Tool):
    name = "test"
    description = "Exécute les tests d'un projet. Détecte automatiquement le framework de test (pytest, jest, go test, etc.)."
    parameters = {
        "path": {
            "type": "string",
            "description": "Fichier de test ou répertoire du projet",
            "required": True,
        },
        "framework": {
            "type": "string",
            "description": "Framework de test spécifique (optionnel, auto-détecté). Ex: 'pytest', 'jest', 'go', 'cargo'",
        },
        "filter": {
            "type": "string",
            "description": "Filtre pour exécuter des tests spécifiques (ex: nom de test, pattern)",
        },
        "verbose": {
            "type": "boolean",
            "description": "Afficher les détails (défaut: true)",
        },
    }

    async def execute(self, path: str, framework: str = None, filter: str = None,
                      verbose: bool = True, **kwargs) -> ToolResult:
        """Exécute les tests."""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return ToolResult(success=False, output="", error=f"Chemin non trouvé: {path}")

        working_dir = path if os.path.isdir(path) else os.path.dirname(path)

        if framework:
            cmd = self._build_command(framework, path, filter, verbose)
        else:
            cmd = self._auto_detect(path, working_dir, filter, verbose)

        if not cmd:
            return ToolResult(success=False, output="", error="Aucun framework de test détecté.")

        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=working_dir,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except asyncio.TimeoutError:
            process.kill()
            return ToolResult(success=False, output="", error="Tests timeout (300s)")

        output = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        combined = output
        if err:
            combined = f"{output}\n{err}" if output else err

        if len(combined) > 8000:
            combined = combined[:8000] + "\n[...tronqué]"

        if process.returncode == 0:
            return ToolResult(success=True, output=combined)
        return ToolResult(success=False, output=combined, error=f"Tests échoués (code {process.returncode})")

    def _build_command(self, framework: str, path: str, filt: str = None, verbose: bool = True) -> str:
        v = "-v" if verbose else ""

        if framework == "pytest":
            f = f" -k '{filt}'" if filt else ""
            return f"python3 -m pytest {v}{f} '{path}'"
        elif framework == "jest":
            f = f" --testNamePattern='{filt}'" if filt else ""
            return f"npx jest {v}{f} '{path}'"
        elif framework == "go":
            f = f" -run '{filt}'" if filt else ""
            return f"go test {v}{f} ./..."
        elif framework == "cargo":
            f = f" {filt}" if filt else ""
            return f"cargo test{f}"
        elif framework == "unittest":
            return f"python3 -m unittest discover -s '{path}' {v}"
        return f"{framework} '{path}'"

    def _auto_detect(self, path: str, working_dir: str, filt: str = None, verbose: bool = True) -> str | None:
        # Python - pytest
        if os.path.exists(os.path.join(working_dir, "pytest.ini")) or \
           os.path.exists(os.path.join(working_dir, "pyproject.toml")) or \
           os.path.exists(os.path.join(working_dir, "setup.py")):
            return self._build_command("pytest", path, filt, verbose)

        # Node.js - jest
        if os.path.exists(os.path.join(working_dir, "package.json")):
            return self._build_command("jest", path, filt, verbose)

        # Go
        if os.path.exists(os.path.join(working_dir, "go.mod")):
            return self._build_command("go", path, filt, verbose)

        # Rust
        if os.path.exists(os.path.join(working_dir, "Cargo.toml")):
            return self._build_command("cargo", path, filt, verbose)

        # Fallback Python
        if path.endswith(".py") or any(f.endswith(".py") for f in os.listdir(working_dir) if os.path.isfile(os.path.join(working_dir, f))):
            return self._build_command("pytest", path, filt, verbose)

        return None
