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
    "# SYSTÈME D'OUTILS\n\n"
    "IMPORTANT : Pour exécuter des actions (créer des fichiers, lancer des commandes, etc.), "
    "tu DOIS utiliser les outils ci-dessous. Tu ne peux PAS juste écrire du code dans ta réponse — "
    "tu dois l'envoyer via l'outil `write` ou `bash`.\n\n"
    "## Format d'appel d'outil\n\n"
    "Pour appeler un outil, écris EXACTEMENT ce format dans ta réponse :\n\n"
    "```\n"
    '<tool name="nom_outil">\n'
    '{{"parametre": "valeur"}}\n'
    "</tool>\n"
    "```\n\n"
    "## Exemples concrets\n\n"
    "Créer un fichier :\n"
    "```\n"
    '<tool name="write">\n'
    '{{"file_path": "/workspace/index.html", "content": "<html>...</html>"}}\n'
    "</tool>\n"
    "```\n\n"
    "Exécuter une commande :\n"
    "```\n"
    '<tool name="bash">\n'
    '{{"command": "python3 -m http.server 8888"}}\n'
    "</tool>\n"
    "```\n\n"
    "Lire un fichier :\n"
    "```\n"
    '<tool name="read">\n'
    '{{"file_path": "/workspace/app.py"}}\n'
    "</tool>\n"
    "```\n\n"
    "Chercher sur internet :\n"
    "```\n"
    '<tool name="web">\n'
    '{{"action": "search", "query": "python flask tutorial"}}\n'
    "</tool>\n"
    "```\n\n"
    "## Outils disponibles\n\n"
    "{tool_descriptions}\n\n"
    "## Règles critiques\n"
    "1. TOUJOURS utiliser les outils pour agir. Ne jamais juste décrire ce que tu ferais.\n"
    "2. Tu peux mettre PLUSIEURS blocs <tool> dans une même réponse.\n"
    "3. Après chaque outil exécuté, tu recevras le résultat et tu pourras continuer.\n"
    "4. Quand tu as TERMINÉ ta tâche, écris : TÂCHE TERMINÉE\n"
    "5. Tant que tu n'as pas écrit TÂCHE TERMINÉE, continue à travailler.\n"
    "---\n"
)


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
    """Parse les appels d'outils depuis le texte de la réponse."""
    tool_calls = []
    # Pattern pour matcher <tool name="...">...</tool> (avec ou sans backticks autour)
    pattern = r'<tool\s+name=["\']([^"\']+)["\']>\s*(.*?)\s*</tool>'
    matches = re.finditer(pattern, text, re.DOTALL)

    for i, match in enumerate(matches):
        name = match.group(1).strip()
        args_str = match.group(2).strip()

        try:
            arguments = json.loads(args_str)
        except json.JSONDecodeError:
            try:
                json_match = re.search(r'\{.*\}', args_str, re.DOTALL)
                if json_match:
                    arguments = json.loads(json_match.group(0))
                else:
                    arguments = {"_raw": args_str}
            except Exception:
                arguments = {"_raw": args_str}

        tool_calls.append(ToolCall(
            id=f"call_{i}",
            name=name,
            arguments=arguments,
        ))

    return tool_calls


def strip_tool_calls(text: str) -> str:
    """Retire les blocs <tool> du texte pour l'affichage."""
    cleaned = re.sub(r'```\s*\n*<tool\s+name=["\'][^"\']+["\']>\s*.*?\s*</tool>\s*\n*```', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'<tool\s+name=["\'][^"\']+["\']>\s*.*?\s*</tool>', '', cleaned, flags=re.DOTALL)
    return cleaned.strip()


def is_task_complete(text: str) -> bool:
    """Vérifie si le modèle indique que la tâche est terminée."""
    markers = [
        "TÂCHE TERMINÉE",
        "TACHE TERMINEE",
        "TÂCHE COMPLÈTE",
        "MISSION ACCOMPLIE",
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

            # Exécuter les tool calls
            if tool_calls:
                self._consecutive_no_tools = 0
                results = []
                for tool_call in tool_calls:
                    result = await self._execute_tool(tool_call)
                    results.append(f"[{tool_call.name}] {result}")

                combined_results = "\n---\n".join(results)
                self.session.add_message("user", f"Résultats des outils :\n{combined_results}\n\nContinue ton travail. Utilise les outils pour la prochaine étape.")
            else:
                # Pas de tool calls détectés
                self._consecutive_no_tools += 1

                # Vérifier si la tâche est terminée
                if is_task_complete(response.content):
                    self._running = False
                elif self._consecutive_no_tools >= 3:
                    # Le modèle ne veut pas utiliser les outils, on arrête
                    self.on_event(EngineEvent("error", {
                        "message": "L'agent n'utilise pas les outils. Essaie de reformuler ta demande.",
                    }))
                    self._running = False
                else:
                    # Relancer le modèle en lui rappelant d'utiliser les outils
                    self.session.add_message("user",
                        "Tu dois utiliser les outils pour agir ! Écris des blocs <tool name=\"...\"> pour créer des fichiers, exécuter des commandes, etc. "
                        "Ne te contente pas de décrire, EXÉCUTE avec les outils. Continue ton travail."
                    )

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

            if tool_calls:
                results = []
                for tool_call in tool_calls:
                    yield EngineEvent("tool_call", {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    })
                    result = await self._execute_tool(tool_call)
                    results.append(f"[{tool_call.name}] {result}")
                    yield EngineEvent("tool_result", {
                        "name": tool_call.name,
                        "success": "ERREUR" not in result,
                        "output": result,
                    })

                combined_results = "\n---\n".join(results)
                self.session.add_message("user", f"Résultats des outils :\n{combined_results}\n\nContinue.")
            elif is_task_complete(response.content):
                self._running = False
            else:
                self.session.add_message("user", "Utilise les outils <tool> pour agir. Continue.")

        yield EngineEvent("done", {"total_steps": self._step})
        self.session.save()

    def stop(self):
        """Arrête l'exécution."""
        self._running = False

    async def close(self):
        """Ferme les connexions."""
        await self.client.close()
