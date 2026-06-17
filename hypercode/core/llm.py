"""Client Ollama API pour HyperCode."""

import json
import httpx
from typing import AsyncGenerator, Optional
from dataclasses import dataclass, field


@dataclass
class Message:
    """Un message dans la conversation."""
    role: str  # system, user, assistant, tool
    content: str
    tool_calls: list = field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass
class ToolCall:
    """Un appel d'outil demandé par le modèle."""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Réponse du LLM."""
    content: str = ""
    tool_calls: list = field(default_factory=list)
    done: bool = False
    total_duration: int = 0
    eval_count: int = 0
    eval_duration: int = 0

    @property
    def tokens_per_second(self) -> float:
        if self.eval_duration > 0:
            return self.eval_count / (self.eval_duration / 1e9)
        return 0.0


class OllamaClient:
    """Client pour l'API Ollama."""

    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host.rstrip("/")
        self.client = httpx.AsyncClient(timeout=600.0)

    async def list_models(self) -> list[dict]:
        """Liste les modèles disponibles."""
        try:
            resp = await self.client.get(f"{self.host}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])
        except Exception as e:
            return []

    async def list_running(self) -> list[dict]:
        """Liste les modèles en cours d'exécution."""
        try:
            resp = await self.client.get(f"{self.host}/api/ps")
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])
        except Exception:
            return []

    async def check_connection(self) -> bool:
        """Vérifie la connexion à Ollama."""
        try:
            resp = await self.client.get(f"{self.host}/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        model: str,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        num_ctx: int = 16384,
        num_predict: int = 4096,
    ) -> LLMResponse:
        """Envoie un message et attend la réponse complète."""
        payload = {
            "model": model,
            "messages": [self._format_message(m) for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
        }
        if tools:
            payload["tools"] = tools

        resp = await self.client.post(
            f"{self.host}/api/chat",
            json=payload,
            timeout=600.0,
        )
        resp.raise_for_status()
        data = resp.json()

        response = LLMResponse(
            content=data.get("message", {}).get("content", ""),
            done=data.get("done", False),
            total_duration=data.get("total_duration", 0),
            eval_count=data.get("eval_count", 0),
            eval_duration=data.get("eval_duration", 0),
        )

        # Parse tool calls
        tool_calls_raw = data.get("message", {}).get("tool_calls", [])
        for i, tc in enumerate(tool_calls_raw):
            func = tc.get("function", {})
            response.tool_calls.append(ToolCall(
                id=f"call_{i}",
                name=func.get("name", ""),
                arguments=func.get("arguments", {}),
            ))

        return response

    async def chat_stream(
        self,
        model: str,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        num_ctx: int = 16384,
    ) -> AsyncGenerator[str, None]:
        """Envoie un message et stream la réponse."""
        payload = {
            "model": model,
            "messages": [self._format_message(m) for m in messages],
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
            },
        }
        if tools:
            payload["tools"] = tools

        async with self.client.stream(
            "POST",
            f"{self.host}/api/chat",
            json=payload,
            timeout=600.0,
        ) as resp:
            async for line in resp.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    def _format_message(self, msg: Message) -> dict:
        """Formate un message pour l'API."""
        formatted = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            formatted["tool_calls"] = [
                {
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                }
                for tc in msg.tool_calls
            ]
        if msg.tool_call_id:
            formatted["tool_call_id"] = msg.tool_call_id
        return formatted

    async def close(self):
        """Ferme le client HTTP."""
        await self.client.aclose()
