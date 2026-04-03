"""Build biomarker context for chat injection."""

import unicodedata


def detect_language(text: str) -> str:
    """Detect language by checking Unicode blocks of the text.

    If mostly Cyrillic characters -> "ru", otherwise "en".
    """
    if not text:
        return "en"

    cyrillic = 0
    latin = 0
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch, "")
        except ValueError:
            continue
        if "CYRILLIC" in name:
            cyrillic += 1
        elif "LATIN" in name:
            latin += 1

    if cyrillic > latin:
        return "ru"
    return "en"


_LABELS = {
    "ru": {
        "intro": (
            "ВАЖНО: Пользователь загрузил результаты лабораторных анализов.\n"
            "Используй эти данные для ПЕРСОНАЛИЗИРОВАННЫХ рекомендаций. "
            "Ссылайся на конкретные значения.\n"
            "НЕ проси пользователя повторно вводить значения, которые уже есть.\n"
            "Отвечай на языке пользователя."
        ),
        "heading": "Результаты анализов пользователя:",
        "high": "ВЫШЕ НОРМЫ",
        "low": "НИЖЕ НОРМЫ",
        "critical": "КРИТИЧНО",
        "ref": "норма:",
    },
    "en": {
        "intro": (
            "IMPORTANT: The user has uploaded lab test results.\n"
            "Use this data for PERSONALIZED recommendations. "
            "Reference specific values.\n"
            "Do NOT ask the user to re-enter values that are already available.\n"
            "Respond in the user's language."
        ),
        "heading": "Lab Results:",
        "high": "HIGH",
        "low": "LOW",
        "critical": "CRITICAL",
        "ref": "ref:",
    },
}


def format_biomarker_context(
    biomarkers: list[dict],
    language: str | None = None,
) -> str | None:
    """Format user's biomarkers into a system message for LLM context."""
    if not biomarkers:
        return None

    lang = language if language in _LABELS else "en"
    lb = _LABELS[lang]

    lines = [
        lb["intro"],
        "",
        lb["heading"],
    ]

    current_cat = None
    for bm in biomarkers:
        cat = bm.get("category", "Другое")
        if cat != current_cat:
            current_cat = cat
            lines.append(f"\n--- {cat} ---")

        name = bm.get("name", "")
        value = bm.get("value", "")
        unit = bm.get("unit", "") or ""
        ref = bm.get("ref_range_text", "") or ""
        status = bm.get("status", "") or ""
        doc_date = str(bm.get("doc_date", ""))[:10]

        status_marker = ""
        if status == "high":
            status_marker = f" [{lb["high"]}]"
        elif status == "low":
            status_marker = f" [{lb["low"]}]"
        elif status == "critical":
            status_marker = f" [{lb["critical"]}]"

        line = f"  {name}: {value} {unit}"
        if ref:
            line += f" ({lb["ref"]} {ref})"
        line += status_marker
        if doc_date:
            line += f" [{doc_date}]"
        lines.append(line)

    return "\n".join(lines)
