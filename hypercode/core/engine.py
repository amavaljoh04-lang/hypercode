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
    "\n## OUTILS DISPONIBLES\n\n"
    "Tu peux utiliser des outils en écrivant des blocs <tool> dans ta réponse.\n"
    "Format EXACT à respecter :\n\n"
    '<tool name="NOM_OUTIL">\n'
    '{{"param1": "valeur1", "param2": "valeur2"}}\n'
    "</tool>\n\n"
    "### Outils :\n\n"
    "{tool_descriptions}\n\n"
    "## RÈGLES D'UTILISATION DES OUTILS\n"
    "- Utilise UN SEUL outil par bloc <tool>\n"
    "- Tu peux utiliser PLUSIEURS outils dans une même réponse\n"
    "- Après chaque outil, tu recevras le résultat et tu pourras continuer\n"
    "- Les paramètres sont en JSON\n"
    "- N'invente PAS de paramètres qui n'existent pas\n"
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
    # Pattern pour matcher <tool name="...">...</tool>
    pattern = r'<tool\s+name=["\']([^"\']+)["\']>\s*(.*?)\s*</tool>'
    matches = re.finditer(pattern, text, re.DOTALL)

    for i, match in enumerate(matches):
        name = match.group(1).strip()
        args_str = match.group(2).strip()

        try:
            arguments = json.loads(args_str)
        except json.JSONDecodeError:
            # Essayer de réparer le JSON
            try:
                # Parfois le modèle met du texte avant/après le JSON
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
    cleaned = re.sub(r'<tool\s+name=["\'][^"\']+["\']>\s*.*?\s*</tool>', '', text, flags=re.DOTALL)
    return cleaned.strip()


@dataclass
class EngineEvent:
    """Événement émis par le moteur."""
    type: str  # thinking, content, tool_call, tool_result, error, done, status
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

        # Construire le prompt système complet avec les outils
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
        self._max_steps = 50

    async def run(self, user_message: str, working_dir: str = "") -> str:
        """Exécute une conversation complète avec l'agent."""
        self.session.working_dir = working_dir
        self.session.add_message("user", user_message)
        self._running = True
        self._step = 0

        final_response = ""

        while self._running and self._step < self._max_steps:
            self._step += 1
            self.on_event(EngineEvent("status", {
                "step": self._step,
                "message": f"Étape {self._step}...",
            }))

            # Appel LLM (sans tools natif — on utilise le prompt)
            self.on_event(EngineEvent("thinking", {"step": self._step}))

            start_time = time.time()
            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=self.session.get_messages_for_llm(),
                    tools=None,  # Pas de tool calling natif
                    temperature=self.config["ollama"]["temperature"],
                    num_ctx=self.config["ollama"]["context_length"],
                )
            except Exception as e:
                self.on_event(EngineEvent("error", {"message": str(e)}))
                self._running = False
                break

            elapsed = time.time() - start_time

            # Parser les tool calls depuis le texte
            tool_calls = parse_tool_calls(response.content)
            display_text = strip_tool_calls(response.content)

            # Afficher le contenu textuel (sans les blocs tool)
            if display_text:
                self.on_event(EngineEvent("content", {
                    "text": display_text,
                    "duration": elapsed,
                    "tokens_per_second": response.tokens_per_second,
                }))
                final_response = display_text

            # Sauvegarder la réponse complète dans la session
            self.session.add_message("assistant", response.content)

            # Exécuter les tool calls
            if tool_calls:
                results = []
                for tool_call in tool_calls:
                    result = await self._execute_tool(tool_call)
                    results.append(f"[{tool_call.name}] {result}")

                # Envoyer les résultats comme message tool
                combined_results = "\n---\n".join(results)
                self.session.add_message("user", f"Résultats des outils :\n{combined_results}")
            else:
                # Pas de tool calls = réponse finale
                self._running = False

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

        # Vérifier les permissions
        permission = self.config["permissions"].get(tool_call.name, "allow")
        if permission == "deny":
            error_msg = f"Permission refusée pour l'outil: {tool_call.name}"
            self.on_event(EngineEvent("tool_result", {
                "name": tool_call.name,
                "success": False,
                "output": error_msg,
            }))
            return error_msg

        # Exécuter l'outil
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
                self.session.add_message("user", f"Résultats des outils :\n{combined_results}")
            else:
                self._running = False

        yield EngineEvent("done", {"total_steps": self._step})
        self.session.save()

    def stop(self):
        """Arrête l'exécution."""
        self._running = False

    async def close(self):
        """Ferme les connexions."""
        await self.client.close()
