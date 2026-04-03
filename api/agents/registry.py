"""Agent registry and lifecycle management."""

from __future__ import annotations
import json as _json

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


# ---------------------------------------------------------------------------
# Agent catalog (HTTP-facing config management for user-facing agents)
# ---------------------------------------------------------------------------

from api.agents.models import AgentConfigInput, AgentInfo

AGENT_CATALOG: dict[str, dict[str, Any]] = {
    "price_monitor": {
        "name_ru": "Мониторинг цен",
        "name_en": "Price Monitor",
        "description_ru": "Поиск лучших цен на лекарства, БАДы и анализы",
        "description_en": "Find best prices for medications, supplements and lab tests",
        "default_settings": {
            "city": "Москва",
            "categories": ["medication", "supplement", "lab_test"],
            "schedule": "daily",
            "notify_telegram": True,
        },
    },
}


async def get_available_agents(
    pool: asyncpg.Pool | None = None,
    domain_id: str | None = None,
    language: str = "ru",
) -> list[AgentInfo]:
    """Return catalog of available agents, enriched with user config if pool/domain provided."""
    agents: list[AgentInfo] = []
    name_key = f"name_{language}" if f"name_{language}" in list(AGENT_CATALOG.values())[0] else "name_en"
    desc_key = f"description_{language}" if f"description_{language}" in list(AGENT_CATALOG.values())[0] else "description_en"

    config_map: dict[str, asyncpg.Record] = {}
    exec_map: dict[str, asyncpg.Record] = {}

    if pool is not None and domain_id is not None:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT agent_code, is_active, settings FROM agent_config WHERE domain_id = $1",
                __import__("uuid").UUID(domain_id),
            )
            config_map = {r["agent_code"]: r for r in rows}

            exec_rows = await conn.fetch(
                "SELECT DISTINCT ON (agent_code) agent_code, started_at, next_run_at "
                "FROM agent_execution WHERE domain_id = $1 "
                "ORDER BY agent_code, started_at DESC",
                __import__("uuid").UUID(domain_id),
            )
            exec_map = {r["agent_code"]: r for r in exec_rows}

    for code, meta in AGENT_CATALOG.items():
        cfg = config_map.get(code)
        exe = exec_map.get(code)
        agents.append(
            AgentInfo(
                code=code,
                name=meta.get(name_key, meta["name_en"]),
                description=meta.get(desc_key, meta["description_en"]),
                is_active=cfg["is_active"] if cfg else False,
                settings=cfg["settings"] if cfg else meta["default_settings"],
                last_run=exe["started_at"] if exe else None,
                next_run=exe["next_run_at"] if exe else None,
            )
        )
    return agents


async def get_agent_config(
    pool: asyncpg.Pool, domain_id: str, agent_code: str
) -> AgentConfigInput:
    """Return current config for an agent, or defaults."""
    if agent_code not in AGENT_CATALOG:
        raise ValueError(f"Unknown agent: {agent_code}")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT settings FROM agent_config WHERE domain_id = $1 AND agent_code = $2",
            __import__("uuid").UUID(domain_id),
            agent_code,
        )
    if row:
        return AgentConfigInput(settings=row["settings"])
    return AgentConfigInput(settings=AGENT_CATALOG[agent_code]["default_settings"])


async def save_agent_config(
    pool: asyncpg.Pool, domain_id: str, agent_code: str, settings: dict[str, Any]
) -> None:
    """Upsert agent configuration."""
    if agent_code not in AGENT_CATALOG:
        raise ValueError(f"Unknown agent: {agent_code}")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_config (domain_id, agent_code, settings, updated_at)
            VALUES ($1, $2, $3::text::jsonb, now())
            ON CONFLICT (domain_id, agent_code)
            DO UPDATE SET settings = $3::text::jsonb, updated_at = now()
            """,
            __import__("uuid").UUID(domain_id),
            agent_code,
            _json.dumps(settings),
        )


async def activate_agent(pool: asyncpg.Pool, domain_id: str, agent_code: str) -> None:
    """Activate an agent for a domain (upsert)."""
    if agent_code not in AGENT_CATALOG:
        raise ValueError(f"Unknown agent: {agent_code}")
    default_settings = AGENT_CATALOG[agent_code]["default_settings"]
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_config (domain_id, agent_code, is_active, settings, updated_at)
            VALUES ($1, $2, true, $3::text::jsonb, now())
            ON CONFLICT (domain_id, agent_code)
            DO UPDATE SET is_active = true, updated_at = now()
            """,
            __import__("uuid").UUID(domain_id),
            agent_code,
            _json.dumps(default_settings),
        )


async def deactivate_agent(pool: asyncpg.Pool, domain_id: str, agent_code: str) -> None:
    """Deactivate an agent for a domain."""
    if agent_code not in AGENT_CATALOG:
        raise ValueError(f"Unknown agent: {agent_code}")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE agent_config SET is_active = false, updated_at = now()
            WHERE domain_id = $1 AND agent_code = $2
            """,
            __import__("uuid").UUID(domain_id),
            agent_code,
        )
