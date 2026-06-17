"""Agent Coder — le principal agent de développement."""

from hypercode.agents.base import Agent, AgentConfig

CODER_PROMPT = """Agent codeur autonome. Exécute immédiatement, jamais de question.

FORMAT: <tool name="NOM">{"param": "val"}</tool>
- Créer fichier: <tool name="write">{"file_path": "/chemin", "content": "code"}</tool>
- Commande: <tool name="bash">{"command": "cmd"}</tool>
- Modifier: <tool name="edit">{"file_path": "/chemin", "old_text": "avant", "new_text": "après"}</tool>
- Lire: <tool name="read">{"file_path": "/chemin"}</tool>
- HTTP: <tool name="http">{"url": "http://...", "method": "GET"}</tool>

RÈGLES:
1. JAMAIS de code dans le texte. TOUT dans <tool>.
2. 1-2 outils par réponse max. Attends les résultats.
3. mkdir -p AVANT write.
4. Erreur → corrige.
5. Vérifié → TÂCHE TERMINÉE.
6. Sois BREF.
"""


class CoderAgent(Agent):
    config = AgentConfig(
        name="coder",
        description="Agent de développement principal",
        system_prompt=CODER_PROMPT,
        tools=[
            "bash", "write", "edit", "read", "http",
            "web", "process",
        ],
        temperature=0.3,
        max_steps=30,
    )
