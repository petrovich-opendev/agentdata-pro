"""Context window management for LLM calls."""

import structlog

from api.llm.client import LLMClient

logger = structlog.get_logger()

_RECENT_WINDOW = 10
_SUMMARY_THRESHOLD = 20

_SUMMARY_PROMPT = (
    "Summarize the following conversation concisely, preserving key facts, "
    "user preferences, and health-related details mentioned. "
    "Write the summary in the same language the user used.\n\n"
)


async def get_context_messages(
    all_messages: list[dict],
    system_prompt: str,
    llm_client: LLMClient,
    summary_model: str,
) -> list[dict]:
    """Build the messages array for an LLM call with context trimming.

    - Always includes the system prompt as the first message.
    - If total messages <= SUMMARY_THRESHOLD: include all.
    - If > SUMMARY_THRESHOLD: summarize older messages, keep last RECENT_WINDOW.
    """
    context: list[dict] = [{"role": "system", "content": system_prompt}]

    if len(all_messages) <= _SUMMARY_THRESHOLD:
        for msg in all_messages:
            context.append({"role": msg["role"], "content": msg["content"]})
        return context

    older = all_messages[: -_RECENT_WINDOW]
    recent = all_messages[-_RECENT_WINDOW:]

    summary = await _summarize_messages(older, llm_client, summary_model)
    context.append({
        "role": "system",
        "content": f"Summary of earlier conversation:\n{summary}",
    })

    for msg in recent:
        context.append({"role": msg["role"], "content": msg["content"]})

    return context


async def _summarize_messages(
    messages: list[dict], llm_client: LLMClient, model: str
) -> str:
    """Summarize a list of messages via a non-streaming LLM call."""
    conversation_text = "\n".join(
        f"{msg['role']}: {msg['content']}" for msg in messages
    )
    summary_messages = [
        {"role": "system", "content": _SUMMARY_PROMPT},
        {"role": "user", "content": conversation_text},
    ]

    await logger.ainfo("summarizing_history", message_count=len(messages))
    summary = await llm_client.complete(summary_messages, model)
    await logger.ainfo("history_summarized", summary_length=len(summary))
    return summary
