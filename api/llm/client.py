"""LLM client wrapping AsyncOpenAI SDK for LiteLLM proxy access."""

import json
from collections.abc import AsyncIterator

import httpx
import openai
import structlog

logger = structlog.get_logger()


class LLMClient:
    """Async LLM client configured to talk to LiteLLM proxy."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def stream_chat(
        self, messages: list[dict], model: str
    ) -> AsyncIterator:
        """Start a streaming chat completion and return the async stream."""
        stream = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        return stream

    async def complete(self, messages: list[dict], model: str) -> str:
        """Non-streaming chat completion (used for summarization)."""
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message.content or ""

    async def classify(self, messages: list[dict], model: str) -> dict:
        """Classify intent via LLM with JSON response format.

        Returns parsed JSON dict. On failure, returns default general_chat intent.
        """
        default = {"intent": "general_chat", "entities": []}
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            result = json.loads(content)
            if "intent" not in result:
                await logger.awarning("classify_missing_intent", raw=content)
                return default
            return result
        except (json.JSONDecodeError, openai.APIError) as exc:
            await logger.awarning("classify_failed", error=str(exc))
            return default
