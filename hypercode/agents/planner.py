"""Agent Planner — planification et architecture."""

from hypercode.agents.base import Agent, AgentConfig

PLANNER_PROMPT = """Agent architecte autonome. Analyse et planifie.

FORMAT: <tool name="NOM">{"param": "val"}</tool>

WORKFLOW:
1. bash (tree, ls) pour voir la structure
2. read pour comprendre le code
3. Plan structuré → TÂCHE TERMINÉE

RÈGLES:
1. 1-2 outils par réponse.
2. Ne modifie PAS de fichiers — juste analyse et plan.
3. Sois concis et précis.
4. Fini → TÂCHE TERMINÉE.
"""


class PlannerAgent(Agent):
    config = AgentConfig(
        name="planner",
        description="Planification — analyse et architecture",
        system_prompt=PLANNER_PROMPT,
        tools=[
            "bash", "read", "http", "web",
        ],
        temperature=0.4,
        max_steps=15,
    )
