"""Extract health-relevant facts from user chat messages (rule-based, no LLM)."""

import re
from uuid import UUID

import asyncpg
import structlog

logger = structlog.get_logger()

# --- Extraction patterns ---
# Each pattern: (compiled_regex, fact_type, group_index_for_fact_text)
# group_index=0 means use the full match, group_index=N means use group(N)

_MEDICATION_PATTERNS = [
    # Russian
    (re.compile(r"принимаю\s+(.+?)(?:\s*[,.]|\s+по\b|\s+\d|\s*$)", re.IGNORECASE), "medication", 1),
    (re.compile(r"пью\s+(.+?)(?:\s*[,.]|\s+по\b|\s+\d|\s*$)", re.IGNORECASE), "medication", 1),
    (re.compile(r"назначили\s+(.+?)(?:\s*[,.]|\s+по\b|\s*$)", re.IGNORECASE), "medication", 1),
    (re.compile(r"начала?\s+(?:принимать|пить)\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "medication", 1),
    # English
    (re.compile(r"(?:i(?:'m)?|i am)\s+(?:taking|on)\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "medication", 1),
    (re.compile(r"taking\s+(\w+(?:\s+\d+\s*(?:mg|mcg|ml|г|мг))?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "medication", 1),
    (re.compile(r"on\s+(\w+\s+\d+\s*(?:mg|mcg|ml|г|мг))(?:\s*[,.]|\s*$)", re.IGNORECASE), "medication", 1),
]

_SYMPTOM_PATTERNS = [
    # Russian
    (re.compile(r"болит\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "symptom", 1),
    (re.compile(r"беспокоит\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "symptom", 1),
    (re.compile(r"(?:чувствую|ощущаю)\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "symptom", 1),
    (re.compile(r"(?:появилась?|началась?)\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "symptom", 1),
    # Common symptom keywords (Russian)
    (re.compile(r"(тошнота|головная боль|головокружение|бессонница|слабость|усталость|одышка|изжога|запор|диарея)", re.IGNORECASE), "symptom", 1),
    # English
    (re.compile(r"(?:i have|i feel|experiencing|suffering from)\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "symptom", 1),
    (re.compile(r"pain\s+in\s+(?:my\s+)?(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "symptom", 0),
    (re.compile(r"(headache|nausea|dizziness|insomnia|fatigue|shortness of breath)", re.IGNORECASE), "symptom", 1),
]

_CONDITION_PATTERNS = [
    # Russian
    (re.compile(r"диагноз\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "condition", 1),
    (re.compile(r"у\s+меня\s+(диабет|гипертония|астма|гастрит|анемия|гипотиреоз|гипертиреоз|артрит|остеопороз|жировой гепатоз)\b", re.IGNORECASE), "condition", 1),
    (re.compile(r"(?:поставили|выявили)\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "condition", 1),
    # English
    (re.compile(r"diagnosed\s+with\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "condition", 1),
    (re.compile(r"i\s+have\s+(diabetes|hypertension|asthma|gastritis|anemia|hypothyroidism|arthritis|fatty liver)\b", re.IGNORECASE), "condition", 1),
]

_ALLERGY_PATTERNS = [
    # Russian
    (re.compile(r"аллергия\s+на\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "allergy", 1),
    (re.compile(r"аллергическая\s+реакция\s+на\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "allergy", 1),
    # English
    (re.compile(r"allergic\s+to\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "allergy", 1),
    (re.compile(r"allergy\s+to\s+(.+?)(?:\s*[,.]|\s*$)", re.IGNORECASE), "allergy", 1),
]

_ALL_PATTERNS = (
    _MEDICATION_PATTERNS
    + _SYMPTOM_PATTERNS
    + _CONDITION_PATTERNS
    + _ALLERGY_PATTERNS
)


def _extract_facts_from_text(message_text: str) -> list[dict]:
    """Apply regex patterns to extract health facts from message text.

    Returns list of {'fact_type': str, 'fact_text': str}.
    """
    facts: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for pattern, fact_type, group_idx in _ALL_PATTERNS:
        for match in pattern.finditer(message_text):
            if group_idx == 0:
                text = match.group(0).strip()
            else:
                text = match.group(group_idx).strip()

            # Clean up extracted text
            text = text.rstrip(".,;:!?")
            text = text.strip()

            if not text or len(text) < 2:
                continue

            # Deduplicate within same message
            key = (fact_type, text.lower())
            if key in seen:
                continue
            seen.add(key)

            facts.append({"fact_type": fact_type, "fact_text": text})

    return facts


async def extract_and_store_facts(
    pool: asyncpg.Pool,
    domain_id: str,
    message_text: str,
    message_id: str | None = None,
) -> list[dict]:
    """Extract health facts from a user message and store them in health_facts table.

    Args:
        pool: asyncpg connection pool
        domain_id: UUID string of the domain
        message_text: the user's message text
        message_id: optional UUID string of the chat message

    Returns:
        List of dicts with extracted facts: [{'fact_type': ..., 'fact_text': ...}, ...]
    """
    facts = _extract_facts_from_text(message_text)
    if not facts:
        return []

    domain_uuid = UUID(domain_id)
    msg_uuid = UUID(message_id) if message_id else None

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_domain', $1, true)",
                domain_id,
            )
            for fact in facts:
                await conn.execute(
                    """
                    INSERT INTO health_facts (domain_id, fact_type, fact_text, extracted_from_message_id)
                    VALUES ($1, $2, $3, $4)
                    """,
                    domain_uuid,
                    fact["fact_type"],
                    fact["fact_text"],
                    msg_uuid,
                )

    await logger.ainfo(
        "health_facts_extracted",
        domain_id=domain_id,
        fact_count=len(facts),
        fact_types=[f["fact_type"] for f in facts],
    )

    return facts


async def get_active_facts(
    pool: asyncpg.Pool,
    domain_id: str,
    language: str = "ru",
) -> str:
    """Format active health facts as text for context injection.

    Returns a formatted string like:
        'Known health facts:\nMedications: aspirin 100mg.\nConditions: fatty liver.'
    Or empty string if no facts.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_domain', $1, true)",
                domain_id,
            )
            rows = await conn.fetch(
                """
                SELECT fact_type, fact_text
                FROM health_facts
                WHERE domain_id = $1 AND is_active = true
                ORDER BY fact_type, recorded_at DESC
                """,
                UUID(domain_id),
            )

    if not rows:
        return ""

    # Group by fact_type
    grouped: dict[str, list[str]] = {}
    for row in rows:
        ft = row["fact_type"]
        grouped.setdefault(ft, []).append(row["fact_text"])

    # Labels
    if language == "ru":
        labels = {
            "medication": "Препараты",
            "symptom": "Симптомы",
            "condition": "Диагнозы",
            "allergy": "Аллергии",
            "lifestyle": "Образ жизни",
        }
        header = "Известные факты о здоровье пользователя:"
    else:
        labels = {
            "medication": "Medications",
            "symptom": "Symptoms",
            "condition": "Conditions",
            "allergy": "Allergies",
            "lifestyle": "Lifestyle",
        }
        header = "Known health facts about the user:"

    lines = [header]
    for fact_type in ("medication", "condition", "allergy", "symptom", "lifestyle"):
        if fact_type in grouped:
            label = labels.get(fact_type, fact_type)
            items = ", ".join(grouped[fact_type])
            lines.append(f"{label}: {items}.")

    return "\n".join(lines)
