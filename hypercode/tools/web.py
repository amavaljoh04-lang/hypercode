"""Outil de recherche et récupération web."""

import httpx
import re
from hypercode.tools.base import Tool, ToolResult


class WebTool(Tool):
    name = "web"
    description = "Recherche sur internet ou récupère le contenu d'une URL. Utile pour trouver des solutions à des erreurs, de la documentation, des exemples de code."
    parameters = {
        "action": {
            "type": "string",
            "description": "'search' pour chercher sur le web, 'fetch' pour récupérer une URL",
            "required": True,
            "enum": ["search", "fetch"],
        },
        "query": {
            "type": "string",
            "description": "Terme de recherche ou URL à récupérer",
            "required": True,
        },
    }

    async def execute(self, action: str, query: str, **kwargs) -> ToolResult:
        """Recherche web ou récupération d'URL."""
        if action == "search":
            return await self._search(query)
        elif action == "fetch":
            return await self._fetch(query)
        else:
            return ToolResult(success=False, output="", error=f"Action inconnue: {action}")

    async def _search(self, query: str) -> ToolResult:
        """Recherche via DuckDuckGo HTML."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) HyperCode/0.1"},
                )

                if resp.status_code != 200:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Recherche échouée (HTTP {resp.status_code})",
                    )

                # Extraire les résultats du HTML
                text = resp.text
                results = []

                # Pattern pour extraire les liens et snippets
                links = re.findall(
                    r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                    text, re.DOTALL
                )
                snippets = re.findall(
                    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                    text, re.DOTALL
                )

                for i, (url, title) in enumerate(links[:8]):
                    title_clean = re.sub(r'<[^>]+>', '', title).strip()
                    snippet = ""
                    if i < len(snippets):
                        snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                    results.append(f"{i+1}. {title_clean}\n   {url}\n   {snippet}\n")

                if not results:
                    return ToolResult(
                        success=True,
                        output="Aucun résultat trouvé pour cette recherche.",
                    )

                return ToolResult(
                    success=True,
                    output=f"Résultats pour '{query}':\n\n" + "\n".join(results),
                )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Erreur recherche: {e}")

    async def _fetch(self, url: str) -> ToolResult:
        """Récupère le contenu d'une URL."""
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) HyperCode/0.1"},
                )

                if resp.status_code != 200:
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"HTTP {resp.status_code} pour {url}",
                    )

                content = resp.text

                # Nettoyer le HTML
                content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
                content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
                content = re.sub(r'<[^>]+>', ' ', content)
                content = re.sub(r'\s+', ' ', content).strip()

                if len(content) > 6000:
                    content = content[:6000] + "\n[...tronqué]"

                return ToolResult(success=True, output=content)

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Erreur fetch: {e}")
