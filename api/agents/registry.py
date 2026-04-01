"""Agent registry and lifecycle management."""

from __future__ import annotations

from typing import Any

import asyncpg
import structlog

from api.agents.base import BaseAgent
from api.agents.router_agent import RouterAgent
from api.agents.search_agent import SearchAgent

logger = structlog.get_logger()

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "router": RouterAgent,
    "search": SearchAgent,
}


async def load_domain_config(pool: asyncpg.Pool, domain_type_id: str) -> dict[str, Any]:
    """Load agent configuration from domain_types table."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT router_prompt, search_config, agent_config, ui_config
            FROM domain_types
            WHERE id = $1
            """,
            domain_type_id,
        )

    if row is None:
        await logger.awarning("domain_type_not_found", domain_type_id=domain_type_id)
        return {
            "router_prompt": "",
            "search_config": {},
            "agent_config": {"enabled_agents": ["router", "search"], "models": {}},
        }

    import json

    return {
        "router_prompt": row["router_prompt"],
        "search_config": json.loads(row["search_config"])
        if isinstance(row["search_config"], str)
        else row["search_config"],
        "agent_config": json.loads(row["agent_config"])
        if isinstance(row["agent_config"], str)
        else row["agent_config"],
    }


async def start_agents(
    nc: Any,
    config: dict[str, Any],
    domain_id: str,
    *,
    llm_client: Any = None,
) -> list[BaseAgent]:
    """Instantiate and start all enabled agents.

    Returns list of running agent instances.
    """
    enabled = config.get("agent_config", {}).get("enabled_agents", [])
    agents: list[BaseAgent] = []

    for name in enabled:
        cls = AGENT_REGISTRY.get(name)
        if cls is None:
            await logger.awarning("agent_not_in_registry", agent_name=name)
            continue

        try:
            if cls is RouterAgent:
                agent = cls(nc, config, llm_client)
            else:
                agent = cls(nc, config)
            await agent.start(domain_id)
            agents.append(agent)
        except Exception:
            await logger.aexception("agent_start_failed", agent_name=name)

    await logger.ainfo("agents_started", count=len(agents), enabled=enabled)
    return agents


async def stop_agents(agents: list[BaseAgent]) -> None:
    """Stop all running agents."""
    for agent in agents:
        try:
            await agent.stop()
        except Exception:
            await logger.aexception(
                "agent_stop_failed", agent=agent.__class__.__name__
            )
    await logger.ainfo("agents_stopped", count=len(agents))
