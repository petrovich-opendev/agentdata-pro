"""GigaChat client for testing. Minimal: get token, send message, stream response."""

import ssl
import httpx
import structlog
from collections.abc import AsyncIterator

logger = structlog.get_logger()

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


async def _get_token(auth_key: str) -> str:
    """Get GigaChat access token via OAuth."""
    import uuid
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with httpx.AsyncClient(verify=ssl_ctx, timeout=15.0) as client:
        resp = await client.post(
            OAUTH_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {auth_key}",
            },
            data={"scope": "GIGACHAT_API_PERS"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def gigachat_stream(
    messages: list[dict],
    auth_key: str,
    model: str = "GigaChat",
) -> AsyncIterator[str]:
    """Stream chat completion from GigaChat. Yields text chunks."""
    token = await _get_token(auth_key)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with httpx.AsyncClient(verify=ssl_ctx, timeout=60.0) as client:
        async with client.stream(
            "POST",
            CHAT_URL,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json={
                "model": model,
                "messages": messages,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    return
                import json
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


async def gigachat_complete(
    messages: list[dict],
    auth_key: str,
    model: str = "GigaChat",
) -> str:
    """Non-streaming GigaChat completion."""
    token = await _get_token(auth_key)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with httpx.AsyncClient(verify=ssl_ctx, timeout=60.0) as client:
        resp = await client.post(
            CHAT_URL,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json={
                "model": model,
                "messages": messages,
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
