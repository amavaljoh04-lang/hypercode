"""Outil de gestion des variables d'environnement."""

import os
from hypercode.tools.base import Tool, ToolResult


class EnvTool(Tool):
    name = "env"
    description = "Gère les variables d'environnement: lire, définir, lister. Utile pour configurer l'environnement de développement."
    parameters = {
        "action": {
            "type": "string",
            "description": "'get' pour lire, 'set' pour définir, 'list' pour lister, 'load' pour charger un .env",
            "required": True,
            "enum": ["get", "set", "list", "load"],
        },
        "name": {
            "type": "string",
            "description": "Nom de la variable (pour get/set)",
        },
        "value": {
            "type": "string",
            "description": "Valeur de la variable (pour set)",
        },
        "file_path": {
            "type": "string",
            "description": "Chemin du fichier .env (pour load)",
        },
    }

    async def execute(self, action: str, name: str = None, value: str = None,
                      file_path: str = None, **kwargs) -> ToolResult:
        """Gère les variables d'environnement."""
        if action == "get":
            if not name:
                return ToolResult(success=False, output="", error="name requis pour get")
            val = os.environ.get(name)
            if val is None:
                return ToolResult(success=True, output=f"{name} n'est pas définie")
            return ToolResult(success=True, output=f"{name}={val}")

        elif action == "set":
            if not name or value is None:
                return ToolResult(success=False, output="", error="name et value requis pour set")
            os.environ[name] = value
            return ToolResult(success=True, output=f"{name}={value}")

        elif action == "list":
            env_vars = sorted(os.environ.items())
            output = "\n".join(f"{k}={v[:50]}{'...' if len(v) > 50 else ''}" for k, v in env_vars)
            if len(output) > 3000:
                output = output[:3000] + "\n[...tronqué]"
            return ToolResult(success=True, output=output)

        elif action == "load":
            fp = os.path.expanduser(file_path or ".env")
            if not os.path.exists(fp):
                return ToolResult(success=False, output="", error=f"Fichier non trouvé: {fp}")
            loaded = 0
            with open(fp, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")
                        loaded += 1
            return ToolResult(success=True, output=f"{loaded} variable(s) chargée(s) depuis {fp}")

        return ToolResult(success=False, output="", error=f"Action inconnue: {action}")
