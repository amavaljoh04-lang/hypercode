"""Classe de base pour les outils HyperCode."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolResult:
    """Résultat de l'exécution d'un outil."""
    success: bool
    output: str
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.success:
            return self.output
        return f"ERREUR: {self.error}\n{self.output}" if self.output else f"ERREUR: {self.error}"


class Tool(ABC):
    """Classe abstraite pour un outil."""

    name: str = ""
    description: str = ""
    parameters: dict = {}

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Exécute l'outil avec les paramètres donnés."""
        pass

    def to_schema(self) -> dict:
        """Retourne le schéma JSON de l'outil pour le LLM."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": [
                        k for k, v in self.parameters.items()
                        if v.get("required", False)
                    ],
                },
            },
        }
