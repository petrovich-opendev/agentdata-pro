"""Base agent class for NATS-based agent framework."""

from __future__ import annotations

import abc
import json
from typing import Any

import nats.aio.client
import structlog

logger = structlog.get_logger()


class BaseAgent(abc.ABC):
    """Abstract base agent that subscribes to a NATS subject and handles messages."""

    subject_pattern: str = ""

    def __init__(self, nc: nats.aio.client.Client, config: dict[str, Any]) -> None:
        self._nc = nc
        self._config = config
        self._sub: nats.aio.subscription.Subscription | None = None
        self._domain_id: str | None = None

    async def start(self, domain_id: str) -> None:
        """Subscribe to the agent's NATS subject for the given domain."""
        self._domain_id = domain_id
        subject = self.subject_pattern.format(domain_id=domain_id)
        self._sub = await self._nc.subscribe(subject, cb=self._message_handler)
        await logger.ainfo(
            "agent_started",
            agent=self.__class__.__name__,
            subject=subject,
        )

    async def _message_handler(self, msg: nats.aio.client.Msg) -> None:
        """Internal NATS callback: deserialize, handle, respond."""
        try:
            payload = json.loads(msg.data.decode())
            result = await self.handle(payload)
            if msg.reply:
                await msg.respond(json.dumps(result).encode())
        except Exception:
            await logger.aexception(
                "agent_handle_error",
                agent=self.__class__.__name__,
                subject=msg.subject,
            )
            if msg.reply:
                error_resp = {"error": "internal_agent_error"}
                await msg.respond(json.dumps(error_resp).encode())

    @abc.abstractmethod
    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process an incoming message and return a response dict."""
        ...

    async def publish(self, subject: str, data: dict[str, Any]) -> None:
        """Publish a message to a NATS subject."""
        await self._nc.publish(subject, json.dumps(data).encode())

    async def stop(self) -> None:
        """Unsubscribe from NATS subject."""
        if self._sub is not None:
            await self._sub.unsubscribe()
            await logger.ainfo(
                "agent_stopped",
                agent=self.__class__.__name__,
            )
            self._sub = None
