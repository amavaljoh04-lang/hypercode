"""Agent Researcher — recherche et documentation."""

from hypercode.agents.base import Agent, AgentConfig

RESEARCHER_PROMPT = """Agent recherche autonome. Cherche, analyse, rapporte.

FORMAT: <tool name="NOM">{"param": "val"}</tool>

WORKFLOW:
1. web search pour trouver l'info
2. Analyse et synthèse
3. Rapport structuré → TÂCHE TERMINÉE

RÈGLES:
1. 1-2 outils par réponse. Attends les résultats.
2. Cite les sources (URLs).
3. Sois concis et factuel.
4. Fini → TÂCHE TERMINÉE.
"""


class ResearcherAgent(Agent):
    config = AgentConfig(
        name="researcher",
        description="Recherche — veille techno, documentation",
        system_prompt=RESEARCHER_PROMPT,
        tools=[
            "bash", "write", "read", "http", "web",
        ],
        temperature=0.4,
        max_steps=20,
    )
