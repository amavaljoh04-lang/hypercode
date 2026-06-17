"""Moteur principal de HyperCode — boucle agent avec tool calling prompt-based."""

import asyncio
import json
import re
import time
from typing import Callable, Optional
from dataclasses import dataclass

from hypercode.core.llm import OllamaClient, Message, LLMResponse, ToolCall
from hypercode.core.memory import Session, generate_session_id, truncate_content
from hypercode.tools import get_tool_by_name, ALL_TOOLS
from hypercode.config import load_config


TOOL_INSTRUCTIONS_TEMPLATE = (
    "\n\n---\n"
    "# OUTILS\n\n"
    "⚠️ TOUTE action = bloc <tool>. Code dans ta réponse = texte mort, JAMAIS sauvegardé.\n\n"
    "Format : <tool name=\"NOM\">{{\"param\": \"val\"}}</tool>\n\n"
    "Exemples :\n"
    '<tool name="write">{{"file_path": "/workspace/index.html", "content": "<!DOCTYPE html>\\n<html>\\n<body>Hello</body>\\n</html>"}}</tool>\n'
    '<tool name="bash">{{"command": "mkdir -p /workspace/mon-projet"}}</tool>\n\n'
    "## Outils disponibles\n\n"
    "{tool_descriptions}\n\n"
    "## Règles\n"
    "1. Chaque action = <tool>. Pas de <tool> = pas d'action.\n"
    "2. Max 3 <tool> par réponse. Attends les résultats.\n"
    "3. PAS de ``` autour des <tool>.\n"
    "4. Fin = TÂCHE TERMINÉE (uniquement après vérification).\n"
    "5. ⛔ JAMAIS de code dans le texte. TOUJOURS dans <tool name=\"write\">.\n"
    "---\n"
)

# Messages de rappel quand le modèle n'utilise pas les outils
NUDGE_MESSAGES = [
    "⚠️ Pas d'outil détecté. Utilise <tool name=\"write\"> ou <tool name=\"bash\"> MAINTENANT. Continue ta tâche.",
    "URGENT : Écris un bloc <tool> pour la prochaine action. Ou TÂCHE TERMINÉE si fini.",
    "DERNIER RAPPEL : <tool name=\"bash\">{\"command\": \"ls\"}</tool> — Utilise ce format ou dis TÂCHE TERMINÉE.",
]


def build_tool_descriptions() -> str:
    """Génère la description COMPACTE des outils pour le prompt."""
    descriptions = []
    for tool in ALL_TOOLS:
        params = ", ".join(
            f"{k}{'*' if v.get('required') else ''}"
            for k, v in tool.parameters.items()
        )
        descriptions.append(f"- **{tool.name}**({params}) — {tool.description}")
    return "\n".join(descriptions)


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

    # Essayer de réparer les newlines dans les strings JSON
    # Le modèle écrit souvent des \n littéraux dans le contenu
    try:
        fixed = _fix_json_newlines(text)
        return json.loads(fixed)
    except (json.JSONDecodeError, ValueError):
        pass

    # Essayer de réparer : guillemets simples → doubles
    try:
        fixed = text.replace("'", '"')
        return json.loads(fixed)
    except (json.JSONDecodeError, ValueError):
        pass

    # Dernier recours pour write/edit : extraire file_path et content manuellement
    result = _extract_write_params(text)
    if result:
        return result

    return {"_raw": text}


def _fix_json_newlines(text: str) -> str:
    """Échappe les newlines littéraux à l'intérieur des strings JSON."""
    result = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\':
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch == '\n':
            result.append('\\n')
            continue
        if in_string and ch == '\t':
            result.append('\\t')
            continue
        result.append(ch)
    return ''.join(result)


def _extract_write_params(text: str) -> dict | None:
    """Extrait file_path et content d'un JSON malformé pour write/edit."""
    # Chercher "file_path": "..."
    fp_match = re.search(r'"file_path"\s*:\s*"([^"]+)"', text)
    if not fp_match:
        return None

    file_path = fp_match.group(1)

    # Chercher "content": "..." — prendre tout entre le premier " après content et le dernier "
    content_match = re.search(r'"content"\s*:\s*"', text)
    if not content_match:
        return None

    start = content_match.end()
    # Trouver la fin : dernière occurrence de "}  ou "} dans le texte
    # On cherche le " fermant en tenant compte des escape
    depth = 0
    i = start
    content_chars = []
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text):
            content_chars.append(ch)
            content_chars.append(text[i + 1])
            i += 2
            continue
        if ch == '"':
            # C'est la fin du content
            break
        content_chars.append(ch)
        i += 1

    content = ''.join(content_chars)
    # Décoder les séquences d'échappement
    content = content.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"')

    return {"file_path": file_path, "content": content}


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


def _truncate_results(results: list[str], max_per_result: int = 500) -> str:
    """Tronque les résultats des outils pour économiser du contexte."""
    truncated = []
    for r in results:
        if len(r) > max_per_result:
            truncated.append(r[:max_per_result] + "...[tronqué]")
        else:
            truncated.append(r)
    return "\n---\n".join(truncated)


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
                messages = self.session.get_messages_for_llm(
                    max_tokens=self.config["ollama"]["context_length"] - 2000
                )
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
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
                    combined_results = _truncate_results(results)
                    self.session.add_message("user",
                        f"⚠️ Tu as dit TÂCHE TERMINÉE mais des outils ont ÉCHOUÉ :\n{combined_results}\n\n"
                        "La tâche N'EST PAS terminée. Corrige les erreurs et réessaie. "
                        "Utilise <tool name=\"bash\"> pour créer les répertoires manquants (mkdir -p)."
                    )
                else:
                    combined_results = _truncate_results(results)
                    error_hint = ""
                    if had_errors:
                        error_hint = (
                            "\n⚠️ Des erreurs se sont produites. CORRIGE-LES. "
                            "mkdir -p pour créer les répertoires manquants."
                        )
                    self.session.add_message("user",
                        f"Résultats :\n{combined_results}\n{error_hint}\n"
                        "Continue. Code dans <tool name=\"write\">, JAMAIS dans le texte."
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
                messages = self.session.get_messages_for_llm(
                    max_tokens=self.config["ollama"]["context_length"] - 2000
                )
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
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
                    combined_results = _truncate_results(results)
                    self.session.add_message("user",
                        f"⚠️ TÂCHE TERMINÉE mais des outils ont ÉCHOUÉ :\n{combined_results}\n"
                        "Corrige les erreurs. mkdir -p avant write."
                    )
                else:
                    combined_results = _truncate_results(results)
                    error_hint = ""
                    if had_errors:
                        error_hint = "\n⚠️ ERREURS — corrige avant de continuer."
                    self.session.add_message("user",
                        f"Résultats :\n{combined_results}\n{error_hint}\n"
                        "Continue. Code dans <tool name=\"write\">, JAMAIS dans le texte."
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
