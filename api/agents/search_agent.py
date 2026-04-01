"""SearchAgent — searches the web using duckduckgo-search."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from duckduckgo_search import DDGS

from api.agents.base import BaseAgent

logger = structlog.get_logger()


class SearchAgent(BaseAgent):
    """Subscribes to agents.{domain_id}.search.request and returns web search results."""

    subject_pattern = "agents.{domain_id}.search.request"

    def __init__(self, nc: Any, config: dict[str, Any]) -> None:
        super().__init__(nc, config)
        search_config = config.get("search_config", {})
        self._region: str = search_config.get("region", "ru-ru")
        self._max_results: int = search_config.get("max_results", 10)

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Search the web for the given query.

        Returns: {"results": [{title, url, snippet}, ...], "query": query}
        """
        query = payload.get("query", "")
        if not query:
            return {"results": [], "query": query}

        try:
            raw_results = await asyncio.to_thread(self._search_sync, query)
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw_results
            ]
            await logger.ainfo(
                "search_completed",
                query=query,
                result_count=len(results),
            )
            return {"results": results, "query": query}
        except Exception as exc:
            await logger.awarning("search_failed", query=query, error=str(exc))
            return {"results": [], "query": query, "error": str(exc)}

    def _search_sync(self, query: str) -> list[dict[str, Any]]:
        """Run synchronous DuckDuckGo search (called via to_thread)."""
        with DDGS() as ddgs:
            return list(ddgs.text(query, region=self._region, max_results=self._max_results))
