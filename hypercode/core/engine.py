"""Moteur principal de HyperCode — boucle agent avec tool calling prompt-based."""

import asyncio
import json
import re
import time
from typing import Callable, Optional
from dataclasses import dataclass

from hypercode.core.llm import OllamaClient, Message, LLMResponse, ToolCall
from hypercode.core.memory import Session, generate_session_id
from hypercode.tools import get_tool_by_name, ALL_TOOLS
from hypercode.config import load_config


TOOL_INSTRUCTIONS_TEMPLATE = (
    "\n\n---\n"
    "# SYSTÈME D'OUTILS — LECTURE OBLIGATOIRE\n\n"
    "⚠️ ATTENTION : Tu ne peux PAS agir sans utiliser les outils. "
    "Écrire du code dans ta réponse NE FAIT RIEN. "
    "Seuls les blocs <tool> ci-dessous permettent de créer des fichiers, exécuter des commandes, etc.\n\n"
    "## Comment utiliser un outil\n\n"
    "Écris ce format EXACT (pas dans un bloc de code markdown) :\n\n"
    '<tool name="nom_outil">\n'
    '{{"param": "valeur"}}\n'
    "</tool>\n\n"
    "## Exemples — COPIE CE FORMAT\n\n"
    "Pour créer un fichier :\n\n"
    '<tool name="write">\n'
    '{{"file_path": "/workspace/index.html", "content": "<!DOCTYPE html>\\n<html>\\n<body>Hello</body>\\n</html>"}}\n'
    "</tool>\n\n"
    "Pour exécuter une commande :\n\n"
    '<tool name="bash">\n'
    '{{"command": "cd /workspace && python3 -m http.server 8888"}}\n'
    "</tool>\n\n"
    "Pour lire un fichier :\n\n"
    '<tool name="read">\n'
    '{{"file_path": "/workspace/app.py"}}\n'
    "</tool>\n\n"
    "Pour chercher sur le web :\n\n"
    '<tool name="web">\n'
    '{{"action": "search", "query": "css glassmorphism tutorial 2025"}}\n'
    "</tool>\n\n"
    "Pour voir l'arborescence :\n\n"
    '<tool name="tree">\n'
    '{{"path": "/workspace"}}\n'
    "</tool>\n\n"
    "## Tous les outils disponibles\n\n"
    "{tool_descriptions}\n\n"
    "## Règles ABSOLUES\n"
    "1. CHAQUE action = un bloc <tool>. Pas de bloc = pas d'action.\n"
    "2. Tu peux mettre PLUSIEURS <tool> dans une même réponse.\n"
    "3. N'encadre PAS les blocs <tool> dans des balises markdown ``` — écris-les directement.\n"
    "4. Quand ta tâche est TERMINÉE, écris le mot exact : TÂCHE TERMINÉE\n"
    "5. Tant que tu n'as PAS écrit TÂCHE TERMINÉE, tu DOIS continuer à travailler en utilisant les outils.\n"
    "6. ⛔ N'écris JAMAIS du code (HTML/CSS/JS/Python) dans ta réponse texte. C'est du texte mort. Utilise TOUJOURS <tool name=\"write\"> pour créer un fichier.\n"
    "7. Pour les GROS fichiers (>20 lignes), utilise <tool name=\"write\"> individuellement pour CHAQUE fichier. N'utilise PAS multiwrite pour du gros contenu.\n"
    "---\n"
)

# Messages de rappel quand le modèle n'utilise pas les outils
NUDGE_MESSAGES = [
    (
        "⚠️ Tu n'as pas utilisé d'outil dans ta dernière réponse. "
        "Tu DOIS utiliser les blocs <tool> pour agir. Voici un rappel :\n\n"
        "Pour créer un fichier, écris directement (PAS dans un bloc ```) :\n\n"
        '<tool name="write">\n'
        '{"file_path": "/chemin/fichier", "content": "contenu du fichier"}\n'
        "</tool>\n\n"
        "Pour exécuter une commande :\n\n"
        '<tool name="bash">\n'
        '{"command": "ta commande ici"}\n'
        "</tool>\n\n"
        "Continue ta tâche en utilisant ces outils MAINTENANT."
    ),
    (
        "RAPPEL URGENT : Ta réponse précédente ne contenait aucun outil. "
        "Tu DOIS utiliser le format <tool name=\"...\"> pour agir. "
        "Quelle est la PROCHAINE action concrète ? Écris un bloc <tool> maintenant. "
        "Si tu as terminé, écris : TÂCHE TERMINÉE"
    ),
    (
        "DERNIÈRE CHANCE : Utilise un outil <tool> ou écris TÂCHE TERMINÉE. "
        "Exemple : <tool name=\"bash\">\n{\"command\": \"ls\"}\n</tool>"
    ),
    (
        "Tu dois agir avec <tool> ou dire TÂCHE TERMINÉE. Rien d'autre ne fonctionne."
    ),
]


def build_tool_descriptions() -> str:
    """Génère la description des outils pour le prompt."""
    descriptions = []
    for tool in ALL_TOOLS:
        params_desc = []
        for pname, pinfo in tool.parameters.items():
            required = " (REQUIS)" if pinfo.get("required") else ""
            params_desc.append(f"    - {pname}: {pinfo.get('description', '')}{required}")

        descriptions.append(
            f"**{tool.name}** — {tool.description}\n"
            f"  Paramètres:\n" + "\n".join(params_desc)
        )
    return "\n\n".join(descriptions)


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Parse les appels d'outils depuis le texte — très robuste."""
    tool_calls = []

    # Étape 1 : Retirer les balises markdown ``` qui entourent des blocs <tool>
    # Le modèle fait souvent : ```\n<tool name="bash">...\n</tool>\n```
    cleaned = re.sub(r'```[a-z]*\s*\n?(<tool\s+name=)', r'\1', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'(</tool>)\s*\n?```', r'\1', cleaned, flags=re.IGNORECASE)

    # Étape 2 : Parser les blocs <tool>
    pattern = r'<tool\s+name=["\']([^"\']+)["\']>\s*(.*?)\s*</tool>'
    matches = re.finditer(pattern, cleaned, re.DOTALL)

    for i, match in enumerate(matches):
        name = match.group(1).strip()
        args_str = match.group(2).strip()

        # Nettoyer les backticks qui traînent dans le JSON
        args_str = args_str.strip('`').strip()

        arguments = _parse_json_robust(args_str)

        tool_calls.append(ToolCall(
            id=f"call_{i}",
            name=name,
            arguments=arguments,
        ))

    return tool_calls


def _parse_json_robust(text: str) -> dict:
    """Parse du JSON de façon très tolérante."""
    # Essai direct
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Extraire le premier objet JSON { ... }
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        pass

    # Essayer de réparer : guillemets simples → doubles
    try:
        fixed = text.replace("'", '"')
        return json.loads(fixed)
    except (json.JSONDecodeError, ValueError):
        pass

    return {"_raw": text}


def strip_tool_calls(text: str) -> str:
    """Retire les blocs <tool> du texte pour l'affichage."""
    # D'abord retirer les blocs <tool> entourés de ```
    cleaned = re.sub(r'```[a-z]*\s*\n?\s*<tool\s+name=["\'][^"\']+["\']>\s*.*?\s*</tool>\s*\n?\s*```', '', text, flags=re.DOTALL)
    # Puis retirer les blocs <tool> seuls
    cleaned = re.sub(r'<tool\s+name=["\'][^"\']+["\']>\s*.*?\s*</tool>', '', cleaned, flags=re.DOTALL)
    return cleaned.strip()


def is_task_complete(text: str) -> bool:
    """Vérifie si le modèle indique que la tâche est terminée."""
    markers = [
        "TÂCHE TERMINÉE",
        "TACHE TERMINEE",
        "TÂCHE COMPLÈTE",
        "TACHE COMPLETE",
        "MISSION ACCOMPLIE",
        "MISSION TERMINÉE",
    ]
    upper = text.upper()
    return any(m.upper() in upper for m in markers)


@dataclass
class EngineEvent:
    """Événement émis par le moteur."""
    type: str
    data: dict


class Engine:
    """Moteur d'exécution de l'agent."""

    def __init__(
        self,
        model: str,
        system_prompt: str,
        ollama_host: str = "http://localhost:11434",
        on_event: Optional[Callable[[EngineEvent], None]] = None,
    ):
        self.model = model
        self.client = OllamaClient(host=ollama_host)
        self.on_event = on_event or (lambda e: None)
        self.config = load_config()

        tool_section = TOOL_INSTRUCTIONS_TEMPLATE.format(
            tool_descriptions=build_tool_descriptions()
        )
        self.system_prompt = system_prompt + "\n\n" + tool_section

        self.session = Session(
            id=generate_session_id(),
            model=model,
            agent=self.config["agent"]["default"],
            working_dir="",
        )
        self.session.add_message("system", self.system_prompt)

        self._running = False
        self._step = 0
        self._max_steps = 80
        self._consecutive_no_tools = 0
        self._max_no_tools = len(NUDGE_MESSAGES) + 1  # 5 chances avant d'abandonner

    async def run(self, user_message: str, working_dir: str = "") -> str:
        """Exécute une conversation complète avec l'agent."""
        self.session.working_dir = working_dir
        self.session.add_message("user", user_message)
        self._running = True
        self._step = 0
        self._consecutive_no_tools = 0

        final_response = ""

        while self._running and self._step < self._max_steps:
            self._step += 1
            self.on_event(EngineEvent("status", {
                "step": self._step,
                "message": f"Étape {self._step}...",
            }))

            self.on_event(EngineEvent("thinking", {"step": self._step}))

            start_time = time.time()
            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=self.session.get_messages_for_llm(),
                    tools=None,
                    temperature=self.config["ollama"]["temperature"],
                    num_ctx=self.config["ollama"]["context_length"],
                )
            except Exception as e:
                self.on_event(EngineEvent("error", {"message": str(e)}))
                self._running = False
                break

            elapsed = time.time() - start_time

            # Parser les tool calls (robuste : gère les ``` autour)
            tool_calls = parse_tool_calls(response.content)
            display_text = strip_tool_calls(response.content)

            if display_text:
                self.on_event(EngineEvent("content", {
                    "text": display_text,
                    "duration": elapsed,
                    "tokens_per_second": response.tokens_per_second,
                }))
                final_response = display_text

            self.session.add_message("assistant", response.content)

            # Vérifier si la tâche est terminée
            task_done = is_task_complete(response.content)

            # Exécuter les tool calls (stop-on-error)
            if tool_calls:
                self._consecutive_no_tools = 0
                results = []
                had_errors = False
                critical_tools = {"write", "multiwrite", "bash", "edit", "patch", "replace"}

                for tool_call in tool_calls:
                    # Si un outil critique a échoué, ne pas exécuter les suivants
                    if had_errors and tool_call.name in critical_tools:
                        skip_msg = f"[IGNORÉ — erreur précédente] {tool_call.name}"
                        results.append(f"[{tool_call.name}] {skip_msg}")
                        self.on_event(EngineEvent("tool_result", {
                            "name": tool_call.name,
                            "success": False,
                            "output": skip_msg,
                        }))
                        continue

                    result = await self._execute_tool(tool_call)
                    results.append(f"[{tool_call.name}] {result}")

                    if "ERREUR" in result.upper() and tool_call.name in critical_tools:
                        had_errors = True

                # Si tâche "terminée" mais avec des erreurs → forcer la continuation
                if task_done and not had_errors:
                    self._running = False
                elif task_done and had_errors:
                    # Le modèle dit terminé mais des outils ont échoué
                    combined_results = "\n---\n".join(results)
                    self.session.add_message("user",
                        f"⚠️ Tu as dit TÂCHE TERMINÉE mais des outils ont ÉCHOUÉ :\n{combined_results}\n\n"
                        "La tâche N'EST PAS terminée. Corrige les erreurs et réessaie. "
                        "Utilise <tool name=\"bash\"> pour créer les répertoires manquants (mkdir -p) avant d'écrire les fichiers."
                    )
                else:
                    combined_results = "\n---\n".join(results)
                    error_hint = ""
                    if had_errors:
                        error_hint = (
                            "\n⚠️ Des erreurs se sont produites. Analyse les erreurs ci-dessus et CORRIGE-LES. "
                            "Si c'est un problème de permission, utilise <tool name=\"bash\">{\"command\": \"mkdir -p /chemin\"}</tool> d'abord. "
                        )
                    self.session.add_message("user",
                        f"Résultats des outils :\n{combined_results}\n{error_hint}\n"
                        "Continue. TOUT le code dans <tool name=\"write\">, JAMAIS dans la réponse texte."
                    )
            else:
                # Pas de tool calls détectés
                if task_done:
                    self._running = False
                    continue

                # Réponse vide ou sans outils
                self._consecutive_no_tools += 1

                if self._consecutive_no_tools >= self._max_no_tools:
                    self.on_event(EngineEvent("error", {
                        "message": "L'agent ne répond plus avec des outils après plusieurs rappels. Session terminée.",
                    }))
                    self._running = False
                else:
                    # Envoyer le message de rappel approprié
                    nudge_idx = min(self._consecutive_no_tools - 1, len(NUDGE_MESSAGES) - 1)
                    nudge = NUDGE_MESSAGES[nudge_idx]
                    self.session.add_message("user", nudge)

        if self._step >= self._max_steps:
            self.on_event(EngineEvent("error", {
                "message": f"Limite de {self._max_steps} étapes atteinte",
            }))

        self.on_event(EngineEvent("done", {
            "total_steps": self._step,
            "session_id": self.session.id,
        }))

        self.session.save()
        return final_response

    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """Exécute un appel d'outil."""
        self.on_event(EngineEvent("tool_call", {
            "name": tool_call.name,
            "arguments": tool_call.arguments,
        }))

        tool = get_tool_by_name(tool_call.name)
        if not tool:
            error_msg = f"Outil inconnu: {tool_call.name}"
            self.on_event(EngineEvent("tool_result", {
                "name": tool_call.name,
                "success": False,
                "output": error_msg,
            }))
            return error_msg

        permission = self.config["permissions"].get(tool_call.name, "allow")
        if permission == "deny":
            error_msg = f"Permission refusée pour l'outil: {tool_call.name}"
            self.on_event(EngineEvent("tool_result", {
                "name": tool_call.name,
                "success": False,
                "output": error_msg,
            }))
            return error_msg

        try:
            result = await tool.execute(**tool_call.arguments)
            self.on_event(EngineEvent("tool_result", {
                "name": tool_call.name,
                "success": result.success,
                "output": str(result),
            }))
            return str(result)
        except Exception as e:
            error_msg = f"Erreur lors de l'exécution de {tool_call.name}: {e}"
            self.on_event(EngineEvent("tool_result", {
                "name": tool_call.name,
                "success": False,
                "output": error_msg,
            }))
            return error_msg

    async def chat_stream(self, user_message: str):
        """Version streaming de run() — yield les événements."""
        self.session.add_message("user", user_message)
        self._running = True
        self._step = 0
        self._consecutive_no_tools = 0

        while self._running and self._step < self._max_steps:
            self._step += 1

            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=self.session.get_messages_for_llm(),
                    tools=None,
                    temperature=self.config["ollama"]["temperature"],
                    num_ctx=self.config["ollama"]["context_length"],
                )
            except Exception as e:
                yield EngineEvent("error", {"message": str(e)})
                break

            tool_calls = parse_tool_calls(response.content)
            display_text = strip_tool_calls(response.content)

            if display_text:
                yield EngineEvent("content", {"text": display_text})

            self.session.add_message("assistant", response.content)

            task_done_stream = is_task_complete(response.content)

            if tool_calls:
                self._consecutive_no_tools = 0
                results = []
                had_errors = False
                critical_tools = {"write", "multiwrite", "bash", "edit", "patch", "replace"}

                for tool_call in tool_calls:
                    if had_errors and tool_call.name in critical_tools:
                        skip_msg = f"[IGNORÉ — erreur précédente] {tool_call.name}"
                        results.append(f"[{tool_call.name}] {skip_msg}")
                        yield EngineEvent("tool_result", {
                            "name": tool_call.name,
                            "success": False,
                            "output": skip_msg,
                        })
                        continue

                    yield EngineEvent("tool_call", {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    })
                    result = await self._execute_tool(tool_call)
                    results.append(f"[{tool_call.name}] {result}")
                    is_error = "ERREUR" in result.upper()
                    yield EngineEvent("tool_result", {
                        "name": tool_call.name,
                        "success": not is_error,
                        "output": result,
                    })
                    if is_error and tool_call.name in critical_tools:
                        had_errors = True

                if task_done_stream and not had_errors:
                    self._running = False
                elif task_done_stream and had_errors:
                    combined_results = "\n---\n".join(results)
                    self.session.add_message("user",
                        f"⚠️ Tu as dit TÂCHE TERMINÉE mais des outils ont ÉCHOUÉ :\n{combined_results}\n\n"
                        "La tâche N'EST PAS terminée. Corrige les erreurs et réessaie. "
                        "Utilise <tool name=\"bash\"> pour créer les répertoires manquants (mkdir -p)."
                    )
                else:
                    combined_results = "\n---\n".join(results)
                    error_hint = ""
                    if had_errors:
                        error_hint = (
                            "\n⚠️ Des erreurs se sont produites. CORRIGE-LES avant de continuer. "
                            "mkdir -p pour créer les répertoires manquants."
                        )
                    self.session.add_message("user",
                        f"Résultats des outils :\n{combined_results}\n{error_hint}\n"
                        "Continue. TOUT le code dans <tool name=\"write\">, JAMAIS dans la réponse texte."
                    )
            elif task_done_stream:
                self._running = False
            else:
                self._consecutive_no_tools += 1
                if self._consecutive_no_tools >= self._max_no_tools:
                    yield EngineEvent("error", {"message": "L'agent ne répond plus avec des outils."})
                    self._running = False
                else:
                    nudge_idx = min(self._consecutive_no_tools - 1, len(NUDGE_MESSAGES) - 1)
                    self.session.add_message("user", NUDGE_MESSAGES[nudge_idx])

        yield EngineEvent("done", {"total_steps": self._step})
        self.session.save()

    def stop(self):
        """Arrête l'exécution."""
        self._running = False

    async def close(self):
        """Ferme les connexions."""
        await self.client.close()
