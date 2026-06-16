"""Outil de presse-papier en mémoire pour le partage de données entre outils."""

from hypercode.tools.base import Tool, ToolResult

_clipboard: dict[str, str] = {}


class ClipboardTool(Tool):
    name = "clipboard"
    description = "Presse-papier en mémoire pour stocker et récupérer du texte entre les étapes. Utile pour sauvegarder des résultats intermédiaires."
    parameters = {
        "action": {
            "type": "string",
            "description": "'copy' pour sauvegarder, 'paste' pour récupérer, 'list' pour voir les clés sauvegardées",
            "required": True,
            "enum": ["copy", "paste", "list"],
        },
        "key": {
            "type": "string",
            "description": "Nom/clé pour identifier le contenu (pour copy/paste)",
        },
        "content": {
            "type": "string",
            "description": "Contenu à sauvegarder (pour copy)",
        },
    }

    async def execute(self, action: str, key: str = None, content: str = None, **kwargs) -> ToolResult:
        """Gère le presse-papier."""
        global _clipboard

        if action == "copy":
            if not key or content is None:
                return ToolResult(success=False, output="", error="key et content requis pour copy")
            _clipboard[key] = content
            return ToolResult(success=True, output=f"Sauvegardé dans '{key}' ({len(content)} caractères)")

        elif action == "paste":
            if not key:
                return ToolResult(success=False, output="", error="key requis pour paste")
            if key not in _clipboard:
                return ToolResult(success=False, output="", error=f"Clé '{key}' non trouvée")
            return ToolResult(success=True, output=_clipboard[key])

        elif action == "list":
            if not _clipboard:
                return ToolResult(success=True, output="Presse-papier vide")
            items = [f"  {k}: {len(v)} caractères" for k, v in _clipboard.items()]
            return ToolResult(success=True, output="Presse-papier:\n" + "\n".join(items))

        return ToolResult(success=False, output="", error=f"Action inconnue: {action}")
