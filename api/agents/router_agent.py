"""RouterAgent — classifies user intent via keyword matching + optional LLM."""

from __future__ import annotations

import re
from typing import Any

import structlog

from api.agents.base import BaseAgent

logger = structlog.get_logger()

# Keyword patterns that indicate search intent (Russian + English)
_SEARCH_KEYWORDS = [
    r"куп[иь]ть",
    r"цен[аыуе]",
    r"стоим",
    r"сколько\s+стоит",
    r"где\s+(?:купить|найти|заказать|взять|продают|продаётся)",
    r"аптек",          # stem covers all cases: аптека/аптеки/аптеку/аптеке/аптекой
    r"лаборатори",     # stem covers all cases
    r"клиник",         # stem covers all cases
    r"анализ\w*\s+(?:на|крови|мочи)",
    r"сда[тв]ь\s+(?:анализ|кровь)",
    r"наличи[еи]",
    r"заказать",
    r"доставк",
    r"сравни(?:ть)?",
    r"отзыв",
    r"рейтинг",
    r"дешев",
    r"скидк",
    r"промокод",
    r"магазин",
    r"в\s+какой\s+(?:аптек|клиник|лаборатори|магазин)",
    r"(?:buy|price|where\s+to\s+buy|order|shop|pharmacy|cheapest|cost)",
]

_SEARCH_PATTERN = re.compile("|".join(_SEARCH_KEYWORDS), re.IGNORECASE)


def _extract_entities(message: str) -> list[str]:
    """Extract key noun phrases for search query construction.

    Filters out verbs, pronouns, filler words. Appends commerce hints
    for better web search quality.
    """
    words = message.split()
    stop_words = {
        "и", "в", "на", "с", "у", "к", "о", "а", "но", "не", "да", "по",
        "из", "за", "от", "до", "для", "как", "что", "это", "он", "она",
        "они", "мне", "мой", "моя", "я", "ты", "мы", "вы", "бы", "ли",
        "же", "то", "все", "уже", "ещё", "еще", "так", "где", "когда",
        "может", "можно", "нужно", "надо", "хочу", "хотел", "хотела",
        "подскажите", "скажите", "расскажите", "пожалуйста", "какой",
        "какая", "какое", "какие", "какую", "каком",
        "найди", "найти", "покажи", "помоги", "посмотри", "проверь",
        "подскажи", "сравни", "купить", "купи", "заказать", "закажи",
        "подешевле", "подороже", "побыстрее", "поближе",
        "самый", "самая", "самое", "самые", "очень", "только", "тоже",
    }
    entities = [w for w in words if len(w) > 2 and w.lower() not in stop_words]
    entities = entities[:5]
    if entities:
        entities.append("купить цена")
    return entities


class RouterAgent(BaseAgent):
    """Subscribes to chat.{domain_id}.classify and returns intent classification."""

    subject_pattern = "chat.{domain_id}.classify"

    def __init__(
        self,
        nc: Any,
        config: dict[str, Any],
        llm_client: Any = None,
    ) -> None:
        super().__init__(nc, config)
        self._llm_client = llm_client
        self._router_prompt: str = config.get("router_prompt", "")
        self._model: str = config.get("agent_config", {}).get("models", {}).get(
            "router", "qwen3:14b"
        )

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Classify user message intent.

        Primary: keyword-based classification (instant, no LLM dependency).
        Returns: {"intent": "general_chat"|"search", "entities": [...]}
        """
        user_message = payload.get("message", "")
        default = {"intent": "general_chat", "entities": []}

        if not user_message:
            return default

        # Keyword-based classification (primary, instant)
        if _SEARCH_PATTERN.search(user_message):
            entities = _extract_entities(user_message)
            result = {"intent": "search", "entities": entities}
            await logger.ainfo(
                "router_classified",
                method="keyword",
                intent="search",
                entities=entities,
            )
            return result

        await logger.ainfo(
            "router_classified",
            method="keyword",
            intent="general_chat",
            entities=[],
        )
        return default
