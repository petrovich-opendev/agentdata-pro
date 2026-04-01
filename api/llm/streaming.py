"""SSE streaming helpers for converting OpenAI streams to FastAPI responses."""

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import openai
import structlog
from fastapi.responses import StreamingResponse

logger = structlog.get_logger()


async def sse_stream(
    llm_stream: AsyncIterator,
    on_complete: Callable[[str, dict | None], Awaitable[uuid.UUID]],
) -> AsyncIterator[str]:
    """Convert an AsyncOpenAI stream to SSE-formatted text chunks.

    Args:
        llm_stream: Async iterator from OpenAI streaming API.
        on_complete: Callback invoked with (full_text, usage_dict) after
            streaming finishes. Must return the saved message UUID.
    """
    full_text = ""
    usage = None

    try:
        async for chunk in llm_stream:
            if chunk.usage is not None:
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }

            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    full_text += delta.content
                    event = json.dumps({"token": delta.content, "done": False})
                    yield f"data: {event}\n\n"

        message_id = await on_complete(full_text, usage)

        final_event = json.dumps(
            {"token": "", "done": True, "message_id": str(message_id)}
        )
        yield f"data: {final_event}\n\n"

    except openai.APITimeoutError:
        await logger.aerror("llm_timeout")
        error_event = json.dumps({"error": "LLM request timed out", "done": True})
        yield f"data: {error_event}\n\n"
    except openai.APIConnectionError as exc:
        await logger.aerror("llm_connection_error", detail=str(exc))
        error_event = json.dumps({"error": "LLM connection failed", "done": True})
        yield f"data: {error_event}\n\n"


def create_sse_response(generator: AsyncIterator[str]) -> StreamingResponse:
    """Wrap an async generator in a StreamingResponse with SSE headers."""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def sse_stream_text(
    text_stream: AsyncIterator[str],
    on_complete: Callable[[str, dict | None], Awaitable[uuid.UUID]],
) -> AsyncIterator[str]:
    """Convert a plain-text async iterator to SSE-formatted chunks.

    Used for LLM backends (like GigaChat) that yield raw text strings
    instead of OpenAI-style chunk objects.
    """
    full_text = ""

    try:
        async for text_chunk in text_stream:
            full_text += text_chunk
            event = json.dumps({"token": text_chunk, "done": False})
            yield f"data: {event}\n\n"

        message_id = await on_complete(full_text, None)

        final_event = json.dumps(
            {"token": "", "done": True, "message_id": str(message_id)}
        )
        yield f"data: {final_event}\n\n"

    except Exception as exc:
        await logger.aerror("gigachat_stream_error", detail=str(exc))
        error_event = json.dumps({"error": "LLM stream failed", "done": True})
        yield f"data: {error_event}\n\n"
