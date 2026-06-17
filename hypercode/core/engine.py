"""Moteur principal de HyperCode — boucle agent avec tool calling prompt-based."""

import asyncio
import json
import os
import re
import time
from typing import Callable, Optional
from dataclasses import dataclass

from hypercode.core.llm import OllamaClient, Message, LLMResponse, ToolCall
from hypercode.core.memory import Session, generate_session_id, truncate_content
from hypercode.tools import get_tool_by_name, ALL_TOOLS
from hypercode.config import load_config


TOOL_INSTRUCTIONS_TEMPLATE = (
    "\nOutils: {tool_descriptions}\n"
)

NUDGE_MESSAGES = [
    "Rappel: utilise <tool> pour agir. Ou dis TÂCHE TERMINÉE si tout est fait.",
]


def build_tool_descriptions(allowed_tools: list[str] | None = None) -> str:
    """Génère la description ultra-compacte des outils."""
    descriptions = []
    for tool in ALL_TOOLS:
        if allowed_tools and tool.name not in allowed_tools:
            continue
        params = ", ".join(tool.parameters.keys())
        descriptions.append(f"- {tool.name}({params})")
    return "\n".join(descriptions)


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Parse les appels d'outils depuis le texte — très robuste."""
    tool_calls = []

    # Étape 1 : Retirer les balises markdown ``` qui entourent des blocs <tool>
    cleaned = re.sub(r'```[a-z]*\s*\n?(<tool\s+name=)', r'\1', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'(</tool>)\s*\n?```', r'\1', cleaned, flags=re.IGNORECASE)

    # Étape 2 : Parser les blocs <tool>
    pattern = r'<tool\s+name=["\']([^"\']+)["\']>\s*(.*?)\s*</tool>'
    matches = re.finditer(pattern, cleaned, re.DOTALL)

    for i, match in enumerate(matches):
        name = match.group(1).strip()
        args_str = match.group(2).strip()
        args_str = args_str.strip('`').strip()
        arguments = _parse_json_robust(args_str)
        tool_calls.append(ToolCall(
            id=f"call_{i}",
            name=name,
            arguments=arguments,
        ))

    # Étape 3 : Détecter les JSON bruts (sans <tool> wrapper)
    # Le modèle écrit parfois juste {"file_path": "...", "content": "..."} dans le texte
    if not tool_calls:
        bare_calls = _detect_bare_json_tools(text)
        tool_calls.extend(bare_calls)

    return tool_calls


def _detect_bare_json_tools(text: str) -> list[ToolCall]:
    """Détecte les appels d'outils JSON bruts sans balise <tool>."""
    calls = []
    # Chercher les patterns JSON qui ressemblent à des write/bash/edit
    # Pattern: {"file_path": "...", "content": "..."} ou {"command": "..."}
    json_pattern = r'\{\s*"(file_path|command|action)"\s*:'
    for match in re.finditer(json_pattern, text):
        # Extraire le JSON complet à partir de cette position
        start = match.start()
        # Trouver l'objet JSON
        brace_count = 0
        end = start
        for j in range(start, len(text)):
            if text[j] == '{':
                brace_count += 1
            elif text[j] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = j + 1
                    break
        if end > start:
            json_str = text[start:end]
            args = _parse_json_robust(json_str)
            if '_raw' not in args:
                # Déterminer le type d'outil
                if 'file_path' in args and 'content' in args:
                    calls.append(ToolCall(id=f"bare_{len(calls)}", name="write", arguments=args))
                elif 'command' in args:
                    calls.append(ToolCall(id=f"bare_{len(calls)}", name="bash", arguments=args))
    return calls


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
    """Retire les blocs <tool> et les JSON bruts du texte pour l'affichage."""
    # D'abord retirer les blocs <tool> entourés de ```
    cleaned = re.sub(r'```[a-z]*\s*\n?\s*<tool\s+name=["\'][^"\']+["\']>\s*.*?\s*</tool>\s*\n?\s*```', '', text, flags=re.DOTALL)
    # Puis retirer les blocs <tool> seuls
    cleaned = re.sub(r'<tool\s+name=["\'][^"\']+["\']>\s*.*?\s*</tool>', '', cleaned, flags=re.DOTALL)
    # Retirer les JSON bruts qui sont des tool calls détectés
    # Pattern: {"file_path": "...", "content": "...(très long)"}
    cleaned = re.sub(r'\{\s*"file_path"\s*:.*?"content"\s*:.*\}', '', cleaned, flags=re.DOTALL)
    # Pattern: {"command": "..."}
    cleaned = re.sub(r'\{\s*"command"\s*:.*?\}', '', cleaned, flags=re.DOTALL)
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


def _truncate_results(results: list[str], max_per_result: int = 300) -> str:
    """Tronque les résultats pour économiser du contexte."""
    truncated = []
    for r in results:
        if len(r) > max_per_result:
            truncated.append(r[:max_per_result] + "...")
        else:
            truncated.append(r)
    return "\n".join(truncated)


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
        allowed_tools: list[str] | None = None,
    ):
        self.model = model
        self.client = OllamaClient(host=ollama_host)
        self.on_event = on_event or (lambda e: None)
        self.config = load_config()
        self.allowed_tools = allowed_tools

        tool_section = TOOL_INSTRUCTIONS_TEMPLATE.format(
            tool_descriptions=build_tool_descriptions(allowed_tools)
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
        self._max_steps = 30
        self._consecutive_no_tools = 0
        self._max_no_tools = 2
        self._files_written = set()
        self._repeated_writes = 0
        self._recent_commands = []
        self._last_error = ""
        self._consecutive_blocks = 0
        self._last_tool_sigs = []  # Track consecutive identical calls (doom loop)

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

            # Après 25 étapes, forcer le modèle à conclure
            if self._step == 25:
                self.session.add_message("user",
                    "STOP. Vérifie et dis TÂCHE TERMINÉE maintenant."
                )

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
                    num_predict=4096,
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
                    if had_errors and tool_call.name in critical_tools:
                        skip_msg = f"[IGNORÉ] {tool_call.name}"
                        results.append(f"[{tool_call.name}] {skip_msg}")
                        self.on_event(EngineEvent("tool_result", {
                            "name": tool_call.name,
                            "success": False,
                            "output": skip_msg,
                        }))
                        continue

                    # DOOM LOOP: block if same tool+args called 3x consecutively
                    tc_sig = self._get_tool_sig(tool_call)
                    if self._should_block_loop(tc_sig, tool_call):
                        self._consecutive_blocks += 1
                        block_msg = self._build_doom_loop_message(tool_call)
                        results.append(f"[{tool_call.name}] {block_msg}")
                        self.on_event(EngineEvent("tool_result", {
                            "name": tool_call.name,
                            "success": False,
                            "output": block_msg,
                        }))
                        continue

                    self._consecutive_blocks = 0  # Reset on successful tool execution
                    result = await self._execute_tool(tool_call)
                    results.append(f"[{tool_call.name}] {result}")

                    # After edit: clear loop history so file can be re-read
                    if tool_call.name == "edit" and "ERREUR" not in result.upper():
                        fp = tool_call.arguments.get("file_path", "")
                        if fp:
                            self._clear_loop_history_for_file(fp)

                    # After read or edit on .py file, auto-run to show errors
                    if tool_call.name in ("edit", "read", "write"):
                        fp = tool_call.arguments.get("file_path", "")
                        if fp and fp.endswith(".py") and "ERREUR" not in result.upper():
                            try:
                                proc = await asyncio.create_subprocess_shell(
                                    f"python3 {fp}",
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE,
                                    cwd=self.session.working_dir or os.path.dirname(fp),
                                )
                                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
                                auto_output = (stdout or b"").decode()[:500]
                                auto_err = (stderr or b"").decode()[:500]
                                if proc.returncode == 0:
                                    auto_result = f"[auto-test] OK:\n{auto_output}"
                                else:
                                    auto_result = f"[auto-test] ERREUR:\n{auto_err}"
                                results.append(auto_result)
                                self.on_event(EngineEvent("tool_result", {
                                    "name": "bash",
                                    "success": proc.returncode == 0,
                                    "output": auto_result,
                                }))
                                if proc.returncode != 0:
                                    had_errors = True
                                    self._last_error = auto_err[:500]
                            except Exception:
                                pass

                    if "ERREUR" in result.upper() and tool_call.name in critical_tools:
                        had_errors = True
                        self._last_error = result[:500]

                # Track files written this step for write-loop detection
                step_writes = set()
                for tc in tool_calls:
                    if tc.name in ("write", "multiwrite"):
                        fp = tc.arguments.get("file_path", "")
                        if fp:
                            step_writes.add(fp)
                rewritten = step_writes & self._files_written
                self._files_written.update(step_writes)
                if rewritten:
                    self._repeated_writes += 1

                if task_done and not had_errors:
                    self._running = False
                elif task_done and had_errors:
                    combined_results = _truncate_results(results)
                    self.session.add_message("user",
                        f"Erreurs détectées:\n{combined_results}"
                    )
                elif self._repeated_writes >= 2:
                    # Model keeps rewriting same files — force stop
                    self.session.add_message("user",
                        "⛔ Tu réécris les mêmes fichiers. "
                        "Tout fonctionne déjà. Dis TÂCHE TERMINÉE."
                    )
                else:
                    # Just feed results back
                    combined_results = _truncate_results(results)
                    self.session.add_message("user", combined_results)
            else:
                if task_done:
                    self._running = False
                    continue

                self._consecutive_no_tools += 1
                if self._consecutive_no_tools >= self._max_no_tools:
                    self.on_event(EngineEvent("error", {
                        "message": "Agent ne répond plus.",
                    }))
                    self._running = False
                else:
                    nudge_idx = min(self._consecutive_no_tools - 1, len(NUDGE_MESSAGES) - 1)
                    self.session.add_message("user", NUDGE_MESSAGES[nudge_idx])

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

    def _check_doom_loop(self, tool_call: "ToolCall") -> bool:
        """OpenCode-style doom loop: block if same tool+args called 3+ times consecutively."""
        tc_sig = self._get_tool_sig(tool_call)
        self._last_tool_sigs.append(tc_sig)
        # Keep last 6
        self._last_tool_sigs = self._last_tool_sigs[-6:]
        # Check if last 3 are identical
        if len(self._last_tool_sigs) >= 3:
            last3 = self._last_tool_sigs[-3:]
            if last3[0] == last3[1] == last3[2]:
                return True
        return False

    def _get_tool_sig(self, tool_call: "ToolCall") -> str:
        """Get a signature string for a tool call. Normalizes read-like commands."""
        if tool_call.name == "bash":
            cmd = tool_call.arguments.get("command", "")
            # Normalize: cat/cat -n/head/tail on same file → same signature
            m = re.match(r'(cat|head|tail)\s+(?:-[a-z]+\s+)*(/\S+)', cmd)
            if m:
                return f"read:{m.group(2)}"
            return f"bash:{cmd}"
        elif tool_call.name == "read":
            return f"read:{tool_call.arguments.get('file_path', '')}"
        elif tool_call.name == "write":
            return f"write:{tool_call.arguments.get('file_path', '')}"
        return f"{tool_call.name}:{str(tool_call.arguments)[:80]}"

    def _build_doom_loop_message(self, tool_call: "ToolCall") -> str:
        """Build context-aware doom loop message. If blocking a read, inject file content."""
        fp = tool_call.arguments.get("file_path", "")
        cmd = tool_call.arguments.get("command", "")
        
        # Extract file path from bash cat commands
        if not fp and cmd:
            m = re.search(r'cat\s+(?:-n\s+)?(/\S+)', cmd)
            if m:
                fp = m.group(1)
        
        # If blocking a read/cat and file exists, inject its content
        is_read = tool_call.name == "read" or (tool_call.name == "bash" and "cat " in cmd)
        if is_read and fp and os.path.isfile(fp):
            try:
                with open(fp) as f:
                    content = f.read()
                if len(content) > 3000:
                    content = content[:3000] + "\n...[tronqué]"
                msg = f"⛔ BOUCLE. Voici le contenu de {fp}:\n```\n{content}\n```\n"
                if self._last_error:
                    msg += f"Dernière erreur: {self._last_error[:300]}\n"
                msg += (
                    f'Utilise edit pour corriger:\n'
                    f'<tool name="edit">{{"file_path": "{fp}", '
                    f'"old_text": "ligne exacte à corriger", '
                    f'"new_text": "ligne corrigée"}}</tool>'
                )
                return msg
            except Exception:
                pass
        
        # Generic doom loop message
        msg = f"⛔ BOUCLE DÉTECTÉE ({tool_call.name} x3). Fais une action DIFFÉRENTE."
        if self._last_error:
            msg += f"\nDernière erreur: {self._last_error[:200]}"
        return msg

    def _should_block_loop(self, tc_sig: str, tool_call: "ToolCall") -> bool:
        """Return True if this tool call should be blocked (doom loop detected)."""
        return self._check_doom_loop(tool_call)

    def _clear_loop_history_for_file(self, file_path: str):
        """Clear loop history after a successful edit so the file can be re-read."""
        self._last_tool_sigs = [
            s for s in self._last_tool_sigs
            if file_path not in s
        ]

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

            if self._step == 25:
                self.session.add_message("user",
                    "STOP. Vérifie et dis TÂCHE TERMINÉE maintenant."
                )

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
                    num_predict=4096,
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
                        skip_msg = f"[IGNORÉ] {tool_call.name}"
                        results.append(f"[{tool_call.name}] {skip_msg}")
                        yield EngineEvent("tool_result", {
                            "name": tool_call.name,
                            "success": False,
                            "output": skip_msg,
                        })
                        continue

                    # DOOM LOOP detection
                    tc_sig = self._get_tool_sig(tool_call)
                    if self._should_block_loop(tc_sig, tool_call):
                        self._consecutive_blocks += 1
                        block_msg = self._build_doom_loop_message(tool_call)
                        results.append(f"[{tool_call.name}] {block_msg}")
                        yield EngineEvent("tool_result", {
                            "name": tool_call.name,
                            "success": False,
                            "output": block_msg,
                        })
                        continue

                    self._consecutive_blocks = 0
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
                    # After edit: clear loop history
                    if tool_call.name == "edit" and not is_error:
                        fp = tool_call.arguments.get("file_path", "")
                        if fp:
                            self._clear_loop_history_for_file(fp)

                    # After read/edit/write on .py file, auto-run to show errors
                    if tool_call.name in ("edit", "read", "write") and not is_error:
                        fp = tool_call.arguments.get("file_path", "")
                        if fp and fp.endswith(".py"):
                            try:
                                proc = await asyncio.create_subprocess_shell(
                                    f"python3 {fp}",
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE,
                                    cwd=self.session.working_dir or os.path.dirname(fp),
                                )
                                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
                                auto_out = (stdout or b"").decode()[:500]
                                auto_err = (stderr or b"").decode()[:500]
                                if proc.returncode == 0:
                                    ar = f"[auto-test] OK:\n{auto_out}"
                                else:
                                    ar = f"[auto-test] ERREUR:\n{auto_err}"
                                results.append(ar)
                                yield EngineEvent("tool_result", {
                                    "name": "bash",
                                    "success": proc.returncode == 0,
                                    "output": ar,
                                })
                                if proc.returncode != 0:
                                    had_errors = True
                                    self._last_error = auto_err[:500]
                            except Exception:
                                pass
                    if is_error and tool_call.name in critical_tools:
                        had_errors = True
                        self._last_error = result[:500]

                # Track files written this step for write-loop detection
                step_writes = set()
                for tc in tool_calls:
                    if tc.name in ("write", "multiwrite"):
                        fp = tc.arguments.get("file_path", "")
                        if fp:
                            step_writes.add(fp)
                rewritten = step_writes & self._files_written
                self._files_written.update(step_writes)
                if rewritten:
                    self._repeated_writes += 1

                if task_done_stream and not had_errors:
                    self._running = False
                elif task_done_stream and had_errors:
                    combined_results = _truncate_results(results)
                    self.session.add_message("user",
                        f"Erreurs détectées:\n{combined_results}"
                    )
                elif self._repeated_writes >= 2:
                    self.session.add_message("user",
                        "⛔ Tu réécris les mêmes fichiers. "
                        "Tout fonctionne déjà. Dis TÂCHE TERMINÉE."
                    )
                else:
                    combined_results = _truncate_results(results)
                    self.session.add_message("user", combined_results)
            elif task_done_stream:
                self._running = False
            else:
                self._consecutive_no_tools += 1
                if self._consecutive_no_tools >= self._max_no_tools:
                    yield EngineEvent("error", {"message": "Agent ne répond plus."})
                    self._running = False
                else:
                    self.session.add_message("user", NUDGE_MESSAGES[0])

        yield EngineEvent("done", {"total_steps": self._step})
        self.session.save()

    def stop(self):
        """Arrête l'exécution."""
        self._running = False

    async def close(self):
        """Ferme les connexions."""
        await self.client.close()
