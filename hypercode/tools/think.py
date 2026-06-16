"""Outil de réflexion structurée (comme Anthropic 'think')."""

from hypercode.tools.base import Tool, ToolResult


class ThinkTool(Tool):
    name = "think"
    description = "Espace de réflexion pour organiser tes pensées avant d'agir. Utilise cet outil quand tu dois réfléchir à une approche complexe, analyser un problème, ou planifier plusieurs étapes."
    parameters = {
        "thought": {
            "type": "string",
            "description": "Ta réflexion, analyse, ou raisonnement",
            "required": True,
        },
    }

    async def execute(self, thought: str, **kwargs) -> ToolResult:
        """Enregistre la réflexion."""
        return ToolResult(success=True, output=f"Réflexion enregistrée ({len(thought)} caractères). Continue.")
