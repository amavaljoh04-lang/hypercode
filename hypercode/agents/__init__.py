"""Agents pré-configurés de HyperCode."""

from hypercode.agents.base import Agent, AgentConfig
from hypercode.agents.coder import CoderAgent
from hypercode.agents.planner import PlannerAgent
from hypercode.agents.debugger import DebuggerAgent
from hypercode.agents.researcher import ResearcherAgent

BUILTIN_AGENTS = {
    "coder": CoderAgent,
    "planner": PlannerAgent,
    "debugger": DebuggerAgent,
    "researcher": ResearcherAgent,
}


def get_agent(name: str) -> Agent:
    """Récupère un agent par son nom."""
    agent_class = BUILTIN_AGENTS.get(name)
    if agent_class:
        return agent_class()
    return CoderAgent()  # Défaut


def list_agents() -> list[dict]:
    """Liste tous les agents disponibles."""
    agents = []
    for name, cls in BUILTIN_AGENTS.items():
        agent = cls()
        agents.append({
            "name": name,
            "description": agent.config.description,
            "tools": agent.config.tools,
        })
    return agents
