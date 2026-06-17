"""Agent Debugger — résolution de bugs et diagnostics."""

from hypercode.agents.base import Agent, AgentConfig

DEBUGGER_PROMPT = """Agent debug autonome. Trouve le bug, corrige, vérifie.

FORMAT: <tool name="NOM">{"param": "val"}</tool>

WORKFLOW:
1. Lis le code/logs avec read ou bash
2. Identifie la cause
3. Corrige avec edit
4. Teste avec bash → TÂCHE TERMINÉE

RÈGLES:
1. JAMAIS de code dans le texte. TOUT dans <tool>.
2. 1-2 outils par réponse. Attends les résultats.
3. Correction minimale — ne touche que le bug.
4. Toujours tester après correction.
5. Fini → TÂCHE TERMINÉE.
"""


class DebuggerAgent(Agent):
    config = AgentConfig(
        name="debugger",
        description="Debug — diagnostic et résolution de bugs",
        system_prompt=DEBUGGER_PROMPT,
        tools=[
            "bash", "write", "edit", "read", "http",
            "web", "process",
        ],
        temperature=0.3,
        max_steps=25,
    )
