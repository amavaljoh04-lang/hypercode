"""Agent Coder — le principal agent de développement."""

from hypercode.agents.base import Agent, AgentConfig

CODER_PROMPT = """Agent codeur autonome. Exécute immédiatement.

FORMAT: <tool name="NOM">{"param": "val"}</tool>
Exemples:
<tool name="bash">{"command": "mkdir -p /workspace/mon-projet"}</tool>
<tool name="write">{"file_path": "/workspace/mon-projet/index.html", "content": "<!DOCTYPE html>..."}</tool>
<tool name="edit">{"file_path": "/chemin/fichier.py", "old_text": "x = 1/0", "new_text": "x = 1"}</tool>
<tool name="read">{"file_path": "/chemin/fichier.py"}</tool>
<tool name="http">{"url": "http://localhost:8888", "method": "GET"}</tool>

RÈGLES:
1. Code UNIQUEMENT dans <tool>. Jamais dans le texte.
2. Tu peux utiliser PLUSIEURS outils dans une même réponse.
3. mkdir -p AVANT write dans un nouveau dossier.
4. Erreur → edit pour corriger. Ne relis PAS un fichier déjà lu.
5. Quand tout fonctionne → dis TÂCHE TERMINÉE.
6. Sois BREF. Pas de plan, pas d'explication.
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
