"""Classe de base pour les agents HyperCode."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentConfig:
    """Configuration d'un agent."""
    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=lambda: ["bash", "edit", "read", "write", "search", "git", "web", "todo"])
    temperature: float = 0.7
    max_steps: int = 50
    auto_approve: bool = True


class Agent:
    """Classe de base pour un agent."""

    config: AgentConfig

    def get_system_prompt(self) -> str:
        """Retourne le system prompt de l'agent."""
        return self.config.system_prompt

    def get_tools(self) -> list[str]:
        """Retourne la liste des outils autorisés."""
        return self.config.tools
