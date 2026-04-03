"""Rule-based health query classifier v2.

Maps user messages to observation_type categories, depth, and temporal scope.
Pure keyword matching — no LLM calls, no DB queries.
"""

from typing import Any


# Maps classifier label -> list of DB categories it covers
_LABEL_TO_DB_CATEGORIES: dict[str, list[str]] = {
    "liver": ["LAB/liver"],
    "lipids": ["LAB/lipids"],
    "kidney": ["LAB/kidney"],
    "hormones": ["LAB/hormones"],
    "vitamins": ["LAB/vitamins"],
    "thyroid": ["LAB/thyroid"],
    "hematology": ["LAB/hematology"],
    "BODY": ["BODY"],
    "VITALS": ["VITALS"],
    "FITNESS": ["FITNESS"],
    "NUTRITION": ["NUTRITION"],
    "SLEEP": ["SLEEP"],
    "FACT": ["FACT"],
    "prices": ["prices"],
    "general": [
        "LAB/liver", "LAB/lipids", "LAB/kidney", "LAB/hormones",
        "LAB/vitamins", "LAB/thyroid", "LAB/hematology",
        "LAB/enzymes", "LAB/electrolytes", "LAB/inflammation",
        "LAB/oncology", "LAB/coagulation",
        "BODY", "VITALS",
    ],
}

# Keywords that trigger each label (substring match, lowercased)
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "liver": [
        "печень", "печен", "алт", "аст", "билирубин", "ггт",
        "liver", "alt", "ast", "bilirubin", "ggt",
    ],
    "lipids": [
        "холестерин", "липид", "лпнп", "лпвп", "триглицерид",
        "cholesterol", "ldl", "hdl", "lipid", "triglycerid",
    ],
    "kidney": [
        "почк", "креатинин", "мочевин", "клубочк",
        "kidney", "creatinine", "urea", "gfr",
    ],
    "hormones": [
        "гормон", "тестостерон", "эстрадиол", "пролактин", "кортизол",
        "инсулин", "hormone", "testosterone", "estradiol", "cortisol",
    ],
    "vitamins": [
        "витамин", "ферритин", "железо",
        "vitamin", "ferritin", "iron", "b12", "d3",
    ],
    "thyroid": [
        "щитовид", "ттг", "т3", "т4", "тпо",
        "thyroid", "tsh",
    ],
    "hematology": [
        "гемоглобин", "эритроцит", "лейкоцит", "тромбоцит", "соэ",
        "кровь", "гематокрит", "hemoglobin", "rbc", "wbc",
        "platelet", "hematocrit", "blood count",
    ],
    "BODY": [
        "вес", "рост", "имт", "масс", "тело",
        "weight", "height", "bmi", "body",
    ],
    "VITALS": [
        "давлен", "пульс", "сердцебиен", "температур", "сатурац",
        "pressure", "pulse", "heart rate", "temperature", "spo2",
    ],
    "FITNESS": [
        "шаг", "тренировк", "активност", "бег", "ходьб",
        "steps", "workout", "exercise", "running", "fitness",
    ],
    "NUTRITION": [
        "питан", "калор", "диет", "еда", "рацион", "углевод", "белк", "жир",
        "nutrition", "calorie", "diet", "food", "protein", "carb", "fat",
    ],
    "SLEEP": [
        "сон", "сна", "спал", "бессонниц", "засыпан",
        "sleep", "insomnia",
    ],
    "FACT": [
        "аллерг", "диагноз", "операц", "прививк", "хроническ",
        "allergy", "diagnosis", "surgery", "vaccination", "chronic",
    ],
    "prices": [
        "цена", "стоимост", "дешев", "купить", "аптека", "заказать",
        "где купить", "сколько стоит",
        "price", "cheap", "buy", "pharmacy",
    ],
    "general": [
        "анализ", "результат", "показател", "отклонен", "норма",
        "здоровь", "обзор", "обследован",
        "results", "overview", "checkup", "summary",
    ],
}

DEPTH_KEYWORDS: dict[str, list[str]] = {
    "detail": [
        "подробн", "расскаж", "покажи", "значени", "детал",
        "detail", "explain", "show",
    ],
    "history": [
        "динамик", "тренд", "раньше", "было", "изменил",
        "за полгода", "за месяц", "истори",
        "trend", "history", "over time", "changed",
    ],
}

TEMPORAL_KEYWORDS: dict[str, list[str]] = {
    "trend": [
        "динамик", "тренд", "раньше", "было", "изменил",
        "за полгода", "за месяц",
        "trend", "over time",
    ],
    "compare": [
        "сравни", "разница", "отличи",
        "compare", "diff", "versus",
    ],
}


def _msg_has(msg: str, keywords: list[str]) -> bool:
    """Check if lowered message contains any keyword (substring)."""
    return any(kw in msg for kw in keywords)


def classify_health_query(message: str) -> dict[str, Any]:
    """Classify user message into health data categories, depth, and temporal scope.

    Returns:
        {
            "categories": list[str]  — DB category values (e.g. "LAB/liver", "BODY")
            "depth": "summary" | "detail" | "history"
            "temporal": "latest" | "trend" | "compare"
        }
    """
    msg = message.lower()

    # Collect matched labels
    matched_labels: list[str] = [
        label for label, kws in CATEGORY_KEYWORDS.items()
        if _msg_has(msg, kws)
    ]

    # Expand labels to DB categories, deduplicate preserving order
    seen: set[str] = set()
    categories: list[str] = []
    for label in matched_labels:
        for db_cat in _LABEL_TO_DB_CATEGORIES.get(label, []):
            if db_cat not in seen:
                seen.add(db_cat)
                categories.append(db_cat)

    # Depth: history > detail > summary
    depth = "summary"
    if _msg_has(msg, DEPTH_KEYWORDS["history"]):
        depth = "history"
    elif _msg_has(msg, DEPTH_KEYWORDS["detail"]):
        depth = "detail"

    # Temporal: compare > trend > latest
    temporal = "latest"
    if _msg_has(msg, TEMPORAL_KEYWORDS["compare"]):
        temporal = "compare"
    elif _msg_has(msg, TEMPORAL_KEYWORDS["trend"]):
        temporal = "trend"

    return {
        "categories": categories,
        "depth": depth,
        "temporal": temporal,
    }
