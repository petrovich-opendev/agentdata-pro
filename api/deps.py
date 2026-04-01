"""Dependency injection providers for FastAPI."""

from typing import Any

import asyncpg
import nats.aio.client
from fastapi import Request

from api.llm.client import LLMClient


def get_pool(request: Request) -> asyncpg.Pool:
    """Return the asyncpg connection pool from app state."""
    return request.app.state.pool


def get_llm_client(request: Request) -> LLMClient:
    """Return the LLM client from app state."""
    return request.app.state.llm_client


def get_system_prompt(request: Request) -> str:
    """Return the system prompt loaded at startup."""
    return request.app.state.system_prompt


def get_nats(request: Request) -> nats.aio.client.Client | None:
    """Return the NATS connection from app state, or None if unavailable."""
    return request.app.state.nc


def get_domain_config(request: Request) -> dict[str, Any]:
    """Return the domain config loaded at startup."""
    return request.app.state.domain_config
