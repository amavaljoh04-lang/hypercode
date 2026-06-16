"""Moteur principal de HyperCode — boucle agent avec tool calling."""

import asyncio
import time
from typing import Callable, Optional
from dataclasses import dataclass

from hypercode.core.llm import OllamaClient, Message, LLMResponse, ToolCall
from hypercode.core.memory import Session, generate_session_id
from hypercode.tools import get_tools_schema, get_tool_by_name
from hypercode.config import load_config


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
        self.system_prompt = system_prompt
        self.client = OllamaClient(host=ollama_host)
        self.on_event = on_event or (lambda e: None)
        self.config = load_config()

        self.session = Session(
            id=generate_session_id(),
            model=model,
            agent=self.config["agent"]["default"],
            working_dir="",
        )
        self.session.add_message("system", system_prompt)

        self._running = False
        self._step = 0
        self._max_steps = 50  # Limite pour éviter les boucles infinies

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

            # Appel LLM
            self.on_event(EngineEvent("thinking", {"step": self._step}))

            start_time = time.time()
            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=self.session.get_messages_for_llm(),
                    tools=get_tools_schema(),
                    temperature=self.config["ollama"]["temperature"],
                    num_ctx=self.config["ollama"]["context_length"],
                )
            except Exception as e:
                self.on_event(EngineEvent("error", {"message": str(e)}))
                self._running = False
                break

            elapsed = time.time() - start_time

            # Traiter le contenu textuel
            if response.content:
                self.on_event(EngineEvent("content", {
                    "text": response.content,
                    "duration": elapsed,
                    "tokens_per_second": response.tokens_per_second,
                }))
                final_response = response.content
                self.session.add_message("assistant", response.content)

            # Traiter les appels d'outils
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    result = await self._execute_tool(tool_call)
                    self.session.add_message("tool", result, name=tool_call.name)
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
                    tools=get_tools_schema(),
                    temperature=self.config["ollama"]["temperature"],
                    num_ctx=self.config["ollama"]["context_length"],
                )
            except Exception as e:
                yield EngineEvent("error", {"message": str(e)})
                break

            if response.content:
                yield EngineEvent("content", {"text": response.content})
                self.session.add_message("assistant", response.content)

            if response.tool_calls:
                for tool_call in response.tool_calls:
                    yield EngineEvent("tool_call", {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    })
                    result = await self._execute_tool(tool_call)
                    yield EngineEvent("tool_result", {
                        "name": tool_call.name,
                        "success": "ERREUR" not in result,
                        "output": result,
                    })
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
