"""SearchAgent — searches the web using SearXNG (self-hosted)."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from api.agents.base import BaseAgent

logger = structlog.get_logger()

_SEARXNG_URL = "http://localhost:8888/search"


class SearchAgent(BaseAgent):
    """Subscribes to agents.{domain_id}.search.request and returns web search results."""

    subject_pattern = "agents.{domain_id}.search.request"

    def __init__(self, nc: Any, config: dict[str, Any]) -> None:
        super().__init__(nc, config)
        search_config = config.get("search_config", {})
        self._language: str = search_config.get("language", "ru")
        self._max_results: int = search_config.get("max_results", 10)

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Search the web for the given query via SearXNG.

        Returns: {"results": [{title, url, snippet}, ...], "query": query}
        """
        query = payload.get("query", "")
        if not query:
            return {"results": [], "query": query}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    _SEARXNG_URL,
                    params={
                        "q": query,
                        "format": "json",
                        "language": self._language,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            raw_results = data.get("results", [])
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                }
                for r in raw_results[: self._max_results]
            ]
            await logger.ainfo(
                "search_completed",
                query=query,
                result_count=len(results),
                engine="searxng",
            )
            return {"results": results, "query": query}
        except Exception as exc:
            await logger.awarning("search_failed", query=query, error=str(exc))
            return {"results": [], "query": query, "error": str(exc)}
