"""Targeted data fetcher v2 — query current_profile + observation_type.

Fetches biomarker/health data filtered by categories and formats it
for LLM context injection. Works with the v2 schema:
  observation_type (reference), observation (raw), current_profile (latest).
"""

from datetime import date, timedelta
from decimal import Decimal

import asyncpg

# ~3000 tokens ≈ 12000 chars
_MAX_CHARS = 12_000

_CATEGORY_LABELS_RU: dict[str, str] = {
    "LAB/liver": "Печень",
    "LAB/lipids": "Липиды",
    "LAB/kidney": "Почки",
    "LAB/hormones": "Гормоны",
    "LAB/vitamins": "Витамины и минералы",
    "LAB/thyroid": "Щитовидная железа",
    "LAB/hematology": "Гематология",
    "LAB/enzymes": "Ферменты",
    "LAB/electrolytes": "Электролиты",
    "LAB/inflammation": "Воспаление",
    "LAB/oncology": "Онкомаркеры",
    "LAB/coagulation": "Свертываемость",
    "BODY": "Тело",
    "VITALS": "Жизненные показатели",
    "FITNESS": "Физическая активность",
    "NUTRITION": "Питание",
    "SLEEP": "Сон",
    "FACT": "Факты о здоровье",
}

_CATEGORY_LABELS_EN: dict[str, str] = {
    "LAB/liver": "Liver",
    "LAB/lipids": "Lipids",
    "LAB/kidney": "Kidney",
    "LAB/hormones": "Hormones",
    "LAB/vitamins": "Vitamins & Minerals",
    "LAB/thyroid": "Thyroid",
    "LAB/hematology": "Hematology",
    "LAB/enzymes": "Enzymes",
    "LAB/electrolytes": "Electrolytes",
    "LAB/inflammation": "Inflammation",
    "LAB/oncology": "Oncology markers",
    "LAB/coagulation": "Coagulation",
    "BODY": "Body",
    "VITALS": "Vitals",
    "FITNESS": "Fitness",
    "NUTRITION": "Nutrition",
    "SLEEP": "Sleep",
    "FACT": "Health facts",
}

_TREND_ARROWS = {"rising": "↑", "falling": "↓", "stable": "→", "new": "NEW"}

_PRIORITY_ORDER = {"critical": 0, "important": 1, "routine": 2}


def _fmt(v: Decimal | None) -> str:
    """Format decimal without trailing zeros."""
    if v is None:
        return "—"
    if v == v.to_integral_value():
        return f"{v:g}"
    return f"{v:.1f}"


def _ref_str(low: Decimal | None, high: Decimal | None) -> str:
    if low is not None and high is not None:
        if low == Decimal("0"):
            return f"<{_fmt(high)}"
        return f"{_fmt(low)}–{_fmt(high)}"
    if high is not None:
        return f"<{_fmt(high)}"
    if low is not None:
        return f">{_fmt(low)}"
    return ""


def _truncate_by_priority(
    blocks: list[tuple[int, str]],
    max_chars: int,
) -> str:
    """Join text blocks sorted by priority, truncating if over limit."""
    blocks.sort(key=lambda x: x[0])
    parts: list[str] = []
    total = 0
    for _, text in blocks:
        if total + len(text) > max_chars:
            break
        parts.append(text)
        total += len(text)
    return "\n".join(parts)


def _cat_label(category: str, lang: str) -> str:
    labels = _CATEGORY_LABELS_RU if lang == "ru" else _CATEGORY_LABELS_EN
    return labels.get(category, category)


async def fetch_targeted_data(
    pool: asyncpg.Pool,
    domain_id: str,
    categories: list[str],
    depth: str,
    temporal: str,
    language: str,
) -> str:
    """Fetch health data filtered by categories, formatted per depth.

    Joins current_profile with observation_type to get names, units, ref ranges.
    """
    if not categories:
        return ""

    lang = language if language in ("ru", "en") else "ru"

    if depth == "history":
        return await _fetch_history(pool, domain_id, categories, lang)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                cp.type_code,
                cp.latest_value_numeric,
                cp.latest_value_text,
                cp.latest_date,
                cp.latest_flag,
                cp.prev_value_numeric,
                cp.prev_date,
                cp.trend,
                ot.name_ru,
                ot.name_en,
                ot.category,
                ot.unit,
                ot.ref_range_low,
                ot.ref_range_high,
                ot.priority
            FROM current_profile cp
            JOIN observation_type ot ON ot.code = cp.type_code
            WHERE cp.domain_id = $1
              AND ot.category = ANY($2)
            ORDER BY ot.category, ot.code
            """,
            domain_id,
            categories,
        )

    if not rows:
        return (
            "Нет данных по запрошенным категориям."
            if lang == "ru"
            else "No data for requested categories."
        )

    if depth == "summary":
        return _format_summary(rows, lang)
    return _format_detail(rows, lang)


def _display_value(row: asyncpg.Record, prefix: str = "latest") -> str:
    """Return numeric value formatted, or text value if numeric is None."""
    num = row.get(f"{prefix}_value_numeric")
    if num is not None:
        return _fmt(num)
    text = row.get(f"{prefix}_value_text")
    if text:
        return str(text)
    return "—"


def _format_summary(rows: list[asyncpg.Record], lang: str) -> str:
    """Summary: only abnormal values grouped by category."""
    blocks: list[tuple[int, str]] = []
    by_cat: dict[str, list[asyncpg.Record]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)

    for cat, cat_rows in by_cat.items():
        abnormal = [r for r in cat_rows if r["latest_flag"] not in ("normal", None)]
        if not abnormal:
            continue

        label = _cat_label(cat, lang)
        lines = [f"### {label}"]
        priority_rank = 2

        for r in abnormal:
            name = r["name_ru"] if lang == "ru" else (r["name_en"] or r["type_code"])
            val = _display_value(r)
            unit = r["unit"] or ""
            ref = _ref_str(r["ref_range_low"], r["ref_range_high"])
            trend = _TREND_ARROWS.get(r["trend"], "")
            date_str = r["latest_date"].strftime("%d.%m.%Y")
            norm_word = "норма" if lang == "ru" else "ref"

            line = f"• {name}: {val} {unit}"
            if ref:
                line += f" ({norm_word} {ref})"
            if trend:
                line += f" {trend}"
            line += f" [{date_str}]"

            flag = r["latest_flag"] or ""
            if "critical" in flag:
                line += " — КРИТИЧНО" if lang == "ru" else " — CRITICAL"

            lines.append(line)
            p = _PRIORITY_ORDER.get(r["priority"], 2)
            priority_rank = min(priority_rank, p)

        blocks.append((priority_rank, "\n".join(lines)))

    if not blocks:
        return (
            "Все показатели в запрошенных категориях в норме."
            if lang == "ru"
            else "All markers in requested categories are normal."
        )

    return _truncate_by_priority(blocks, _MAX_CHARS)


def _format_detail(rows: list[asyncpg.Record], lang: str) -> str:
    """Detail: ALL values with ref ranges, trends, previous values."""
    blocks: list[tuple[int, str]] = []
    by_cat: dict[str, list[asyncpg.Record]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)

    for cat, cat_rows in by_cat.items():
        label = _cat_label(cat, lang)
        lines = [f"### {label}"]
        priority_rank = 2

        for r in cat_rows:
            name = r["name_ru"] if lang == "ru" else (r["name_en"] or r["type_code"])
            val = _display_value(r)
            unit = r["unit"] or ""
            ref = _ref_str(r["ref_range_low"], r["ref_range_high"])
            trend = _TREND_ARROWS.get(r["trend"], "")
            date_str = r["latest_date"].strftime("%d.%m.%Y")
            flag = r["latest_flag"] or "normal"
            norm_word = "норма" if lang == "ru" else "ref"

            line = f"• {name}: {val} {unit}"
            if ref:
                line += f" ({norm_word} {ref})"
            if trend:
                line += f" {trend}"
            line += f" [{date_str}] [{flag}]"

            if r["prev_value_numeric"] is not None:
                prev_str = _fmt(r["prev_value_numeric"])
                prev_date = r["prev_date"].strftime("%d.%m.%Y")
                prev_word = "пред." if lang == "ru" else "prev"
                line += f" ({prev_word} {prev_str} {prev_date})"

            lines.append(line)
            p = _PRIORITY_ORDER.get(r["priority"], 2)
            priority_rank = min(priority_rank, p)

        blocks.append((priority_rank, "\n".join(lines)))

    return _truncate_by_priority(blocks, _MAX_CHARS)


async def _fetch_history(
    pool: asyncpg.Pool,
    domain_id: str,
    categories: list[str],
    lang: str,
) -> str:
    """Fetch last 6 months of observations for given categories."""
    six_months_ago = date.today() - timedelta(days=180)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                o.value_numeric,
                o.value_text,
                o.effective_date,
                ot.code,
                ot.name_ru,
                ot.name_en,
                ot.category,
                ot.unit,
                ot.ref_range_low,
                ot.ref_range_high,
                ot.priority
            FROM observation o
            JOIN observation_type ot ON ot.code = o.type_code
            WHERE o.domain_id = $1
              AND ot.category = ANY($2)
              AND o.effective_date >= $3
            ORDER BY ot.category, ot.code, o.effective_date DESC
            """,
            domain_id,
            categories,
            six_months_ago,
        )

    if not rows:
        return (
            "Нет данных за последние 6 месяцев по запрошенным категориям."
            if lang == "ru"
            else "No data for the last 6 months in requested categories."
        )

    blocks: list[tuple[int, str]] = []
    by_cat: dict[str, dict[str, list[asyncpg.Record]]] = {}
    for r in rows:
        cat = r["category"]
        code = r["code"]
        by_cat.setdefault(cat, {}).setdefault(code, []).append(r)

    for cat, type_map in by_cat.items():
        label = _cat_label(cat, lang)
        lines = [f"### {label}"]
        priority_rank = 2

        for code, obs_list in type_map.items():
            first = obs_list[0]
            name = first["name_ru"] if lang == "ru" else (first["name_en"] or code)
            unit = first["unit"] or ""
            ref = _ref_str(first["ref_range_low"], first["ref_range_high"])
            norm_word = "норма" if lang == "ru" else "ref"
            header = f"• {name}"
            if ref:
                header += f" ({norm_word} {ref})"
            header += ":"
            lines.append(header)

            for obs in obs_list:
                val = _fmt(obs["value_numeric"]) if obs["value_numeric"] is not None else (obs["value_text"] or "—")
                d = obs["effective_date"].strftime("%d.%m.%Y")
                lines.append(f"  {d}: {val} {unit}")

            p = _PRIORITY_ORDER.get(first["priority"], 2)
            priority_rank = min(priority_rank, p)

        blocks.append((priority_rank, "\n".join(lines)))

    return _truncate_by_priority(blocks, _MAX_CHARS)


async def fetch_abnormal_alerts(
    pool: asyncpg.Pool,
    domain_id: str,
) -> str:
    """Fetch critical/important abnormal values — always included in context.

    Returns a short alert block for LLM context.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                cp.type_code,
                cp.latest_value_numeric,
                cp.latest_value_text,
                cp.latest_date,
                cp.latest_flag,
                cp.trend,
                ot.name_ru,
                ot.name_en,
                ot.unit,
                ot.ref_range_low,
                ot.ref_range_high,
                ot.priority
            FROM current_profile cp
            JOIN observation_type ot ON ot.code = cp.type_code
            WHERE cp.domain_id = $1
              AND (
                  cp.latest_flag IN ('critical_low', 'critical_high')
                  OR (ot.priority = 'critical' AND cp.latest_flag IS DISTINCT FROM 'normal')
              )
            ORDER BY ot.priority, ot.category, ot.code
            """,
            domain_id,
        )

    if not rows:
        return ""

    lines = ["⚠ ALERTS:"]
    for r in rows:
        name = r["name_ru"]
        val = _fmt(r["latest_value_numeric"]) if r["latest_value_numeric"] is not None else (r["latest_value_text"] or "—")
        unit = r["unit"] or ""
        ref = _ref_str(r["ref_range_low"], r["ref_range_high"])
        trend = _TREND_ARROWS.get(r["trend"], "")
        flag = r["latest_flag"] or ""

        severity = "CRITICAL" if "critical" in flag else "ABNORMAL"
        line = f"• {name}: {val} {unit}"
        if ref:
            line += f" (ref {ref})"
        if trend:
            line += f" {trend}"
        line += f" — {severity}"
        lines.append(line)

    return "\n".join(lines)
