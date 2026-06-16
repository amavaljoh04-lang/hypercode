"""Outil de requêtes HTTP pour tester des APIs."""

import asyncio
import httpx
import json
from hypercode.tools.base import Tool, ToolResult


class HttpTool(Tool):
    name = "http"
    description = "Envoie des requêtes HTTP (GET, POST, PUT, DELETE, etc.). Utile pour tester des APIs, des serveurs, des endpoints."
    parameters = {
        "method": {
            "type": "string",
            "description": "Méthode HTTP: GET, POST, PUT, DELETE, PATCH, HEAD",
            "required": True,
        },
        "url": {
            "type": "string",
            "description": "URL complète de la requête",
            "required": True,
        },
        "headers": {
            "type": "object",
            "description": "Headers HTTP (optionnel, ex: {\"Content-Type\": \"application/json\"})",
        },
        "body": {
            "type": "string",
            "description": "Corps de la requête (pour POST/PUT/PATCH)",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout en secondes (défaut: 15)",
        },
    }

    async def execute(self, method: str = "GET", url: str = "", headers: dict = None, body: str = None,
                      timeout: int = 15, **kwargs) -> ToolResult:
        """Envoie une requête HTTP avec retry automatique pour localhost."""
        if not url:
            return ToolResult(success=False, output="", error="URL requise")

        method = method.upper()
        valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
        if method not in valid_methods:
            return ToolResult(success=False, output="", error=f"Méthode invalide: {method}")

        # Retry pour localhost (le serveur peut mettre du temps à démarrer)
        is_local = "localhost" in url or "127.0.0.1" in url
        max_retries = 3 if is_local else 1
        last_error = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=float(timeout), follow_redirects=True) as client:
                    request_kwargs = {
                        "method": method,
                        "url": url,
                        "headers": headers or {},
                    }

                    if body and method in {"POST", "PUT", "PATCH"}:
                        try:
                            json_body = json.loads(body)
                            request_kwargs["json"] = json_body
                        except (json.JSONDecodeError, TypeError):
                            request_kwargs["content"] = body

                    resp = await client.request(**request_kwargs)

                    # Formater la réponse
                    output_parts = [
                        f"HTTP {resp.status_code} {resp.reason_phrase}",
                        f"URL: {resp.url}",
                    ]

                    important_headers = ["content-type", "content-length", "location", "set-cookie"]
                    for h in important_headers:
                        if h in resp.headers:
                            output_parts.append(f"{h}: {resp.headers[h]}")

                    content = resp.text
                    if len(content) > 3000:
                        content = content[:3000] + "\n[...tronqué]"
                    if content:
                        output_parts.append(f"\nCorps:\n{content}")

                    return ToolResult(
                        success=200 <= resp.status_code < 400,
                        output="\n".join(output_parts),
                        error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
                    )

            except (httpx.TimeoutException, httpx.ConnectError, Exception) as e:
                last_error = str(e)
                if attempt < max_retries - 1 and is_local:
                    await asyncio.sleep(2)

        return ToolResult(success=False, output="", error=last_error)
