"""Three-level natural language health profile summary.

Uses current_profile + observation_type tables (v2 schema).
L1 CRITICAL  — values in critical range or priority=critical with abnormal flag
L2 PROFILE   — abnormal labs, medications/conditions (FACT), body metrics
L3 NORMAL    — count of normal markers + last lab date
"""

from decimal import Decimal
from typing import Any

import asyncpg

_TREND_ARROW = {
    "rising": "↑",
    "falling": "↓",
    "stable": "→",
    "new": "",
}

_FLAG_RU = {
    "critical_low": "⚠ КРИТИЧНО НИЗКО",
    "critical_high": "⚠ КРИТИЧНО ВЫСОКО",
    "low": "↓ ниже нормы",
    "high": "↑ выше нормы",
}

_FLAG_EN = {
    "critical_low": "⚠ CRITICALLY LOW",
    "critical_high": "⚠ CRITICALLY HIGH",
    "low": "↓ below range",
    "high": "↑ above range",
}


def _fmt_num(v: Any) -> str:
    """Format a numeric value without trailing zeros."""
    if v is None:
        return "—"
    d = Decimal(str(v))
    if d == d.to_integral_value():
        return str(int(d))
    return f"{d:.1f}"


def _ref_range_str(ref_low: Any, ref_high: Any) -> str:
    if ref_low is not None and ref_high is not None:
        low = _fmt_num(ref_low)
        high = _fmt_num(ref_high)
        if Decimal(str(ref_low)) == 0:
            return f"<{high}"
        return f"{low}–{high}"
    if ref_high is not None:
        return f"<{_fmt_num(ref_high)}"
    if ref_low is not None:
        return f">{_fmt_num(ref_low)}"
    return ""


def _is_critical(row: asyncpg.Record) -> bool:
    """L1: value in critical range, or priority=critical with non-normal flag."""
    flag = row["latest_flag"]
    val = row["latest_value_numeric"]
    crit_low = row["critical_low"]
    crit_high = row["critical_high"]
    priority = row["priority"]

    # Numeric critical range check
    if val is not None:
        if crit_low is not None and val < crit_low:
            return True
        if crit_high is not None and val > crit_high:
            return True

    # Priority=critical with abnormal flag
    if priority == "critical" and flag not in ("normal", "new"):
        return True

    return False


def _is_abnormal(row: asyncpg.Record) -> bool:
    """L2 check: flag is low or high (but not critical)."""
    return row["latest_flag"] in ("low", "high")


def _is_fact(row: asyncpg.Record) -> bool:
    """L2 check: category=FACT (medication, condition, symptom, allergy)."""
    return row["category"] == "FACT"


def _is_body(row: asyncpg.Record) -> bool:
    """L2 check: body metrics."""
    return row["category"] == "BODY"


def _format_value(row: asyncpg.Record) -> str:
    """Format value depending on type."""
    if row["value_type"] == "text":
        return row["latest_value_text"] or "—"
    return _fmt_num(row["latest_value_numeric"])


def _build_critical_line(row: asyncpg.Record, language: str) -> str:
    """Format one L1 critical line."""
    name = row["name_ru"] if language == "ru" else row["name_en"]
    val = _format_value(row)
    unit = row["unit"] or ""
    ref = _ref_range_str(row["ref_range_low"], row["ref_range_high"])
    trend = _TREND_ARROW.get(row["trend"], "")
    date_str = row["latest_date"].strftime("%d.%m.%Y") if row["latest_date"] else ""

    flag_map = _FLAG_RU if language == "ru" else _FLAG_EN
    flag_label = flag_map.get(row["latest_flag"], "")
    if not flag_label:
        # Determine from value
        val_n = row["latest_value_numeric"]
        if val_n is not None:
            if row["critical_high"] is not None and val_n > row["critical_high"]:
                flag_label = flag_map["critical_high"]
            elif row["critical_low"] is not None and val_n < row["critical_low"]:
                flag_label = flag_map["critical_low"]
            elif row["ref_range_high"] is not None and val_n > row["ref_range_high"]:
                flag_label = flag_map["high"]
            elif row["ref_range_low"] is not None and val_n < row["ref_range_low"]:
                flag_label = flag_map["low"]

    parts = [f"  • {name}: {val} {unit}".rstrip()]
    if ref:
        norm = "норма" if language == "ru" else "ref"
        parts.append(f"({norm} {ref})")
    if trend:
        parts.append(trend)
    if flag_label:
        parts.append(flag_label)
    if date_str:
        parts.append(f"[{date_str}]")
    return " ".join(parts)


def _build_profile_line(row: asyncpg.Record, language: str) -> str:
    """Format one L2 profile line."""
    name = row["name_ru"] if language == "ru" else row["name_en"]
    val = _format_value(row)
    unit = row["unit"] or ""
    trend = _TREND_ARROW.get(row["trend"], "")

    if _is_fact(row):
        # Facts: just name + text value
        return f"  • {name}: {val}"

    parts = [f"  • {name}: {val} {unit}".rstrip()]
    ref = _ref_range_str(row["ref_range_low"], row["ref_range_high"])
    if ref:
        norm = "норма" if language == "ru" else "ref"
        parts.append(f"({norm} {ref})")

    flag_map = _FLAG_RU if language == "ru" else _FLAG_EN
    flag_label = flag_map.get(row["latest_flag"], "")
    if flag_label:
        parts.append(flag_label)
    if trend:
        parts.append(trend)
    return " ".join(parts)


async def build_health_profile(
    pool: asyncpg.Pool,
    domain_id: str,
    language: str = "ru",
) -> dict:
    """Build three-level NL health profile summary.

    Returns:
        {'summary_text': str, 'token_estimate': int}
    """
    query = """
        SELECT
            cp.latest_value_numeric,
            cp.latest_value_text,
            cp.latest_date,
            cp.latest_flag,
            cp.prev_value_numeric,
            cp.prev_date,
            cp.trend,
            ot.code,
            ot.name_ru,
            ot.name_en,
            ot.unit,
            ot.category,
            ot.priority,
            ot.ref_range_low,
            ot.ref_range_high,
            ot.critical_low,
            ot.critical_high,
            ot.value_type
        FROM current_profile cp
        JOIN observation_type ot ON ot.code = cp.type_code
        WHERE cp.domain_id = $1
        ORDER BY
            CASE ot.priority
                WHEN 'critical' THEN 0
                WHEN 'important' THEN 1
                ELSE 2
            END,
            ot.category,
            ot.code
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, domain_id)

    if not rows:
        no_data = (
            "Данные наблюдений отсутствуют."
            if language == "ru"
            else "No observation data available."
        )
        return {"summary_text": no_data, "token_estimate": len(no_data) // 4}

    critical_rows = []
    abnormal_rows = []
    fact_rows = []
    body_rows = []
    normal_count = 0
    last_lab_date = None

    for r in rows:
        # Track latest lab date (LAB/* categories only)
        if r["category"].startswith("LAB") and r["latest_date"] is not None:
            if last_lab_date is None or r["latest_date"] > last_lab_date:
                last_lab_date = r["latest_date"]

        if _is_critical(r):
            critical_rows.append(r)
        elif _is_fact(r):
            fact_rows.append(r)
        elif _is_body(r):
            body_rows.append(r)
        elif _is_abnormal(r):
            abnormal_rows.append(r)
        else:
            normal_count += 1

    lines: list[str] = []

    # --- L1: CRITICAL ---
    if critical_rows:
        header = (
            "🔴 КРИТИЧНЫЕ ПОКАЗАТЕЛИ:" if language == "ru"
            else "🔴 CRITICAL VALUES:"
        )
        lines.append(header)
        for r in critical_rows:
            lines.append(_build_critical_line(r, language))
        lines.append("")

    # --- L2: PROFILE ---
    has_profile = abnormal_rows or fact_rows or body_rows
    if has_profile:
        header = (
            "📋 ПРОФИЛЬ:" if language == "ru"
            else "📋 PROFILE:"
        )
        lines.append(header)

        if abnormal_rows:
            sub = (
                "Отклонения от нормы:" if language == "ru"
                else "Out of range:"
            )
            lines.append(f"  {sub}")
            for r in abnormal_rows:
                lines.append(_build_profile_line(r, language))

        if fact_rows:
            sub = (
                "Препараты / состояния:" if language == "ru"
                else "Medications / conditions:"
            )
            lines.append(f"  {sub}")
            for r in fact_rows:
                lines.append(_build_profile_line(r, language))

        if body_rows:
            sub = (
                "Антропометрия:" if language == "ru"
                else "Body metrics:"
            )
            lines.append(f"  {sub}")
            for r in body_rows:
                lines.append(_build_profile_line(r, language))

        lines.append("")

    # --- L3: NORMAL ---
    if normal_count > 0:
        date_str = last_lab_date.strftime("%d.%m.%Y") if last_lab_date else "—"
        if language == "ru":
            lines.append(
                f"✅ {normal_count} показателей в норме."
                f" Последние анализы: {date_str}."
            )
        else:
            lines.append(
                f"✅ {normal_count} markers within normal range."
                f" Last lab date: {date_str}."
            )

    summary_text = "\n".join(lines).strip()
    token_estimate = len(summary_text) // 4

    return {"summary_text": summary_text, "token_estimate": token_estimate}


async def get_or_refresh_profile_cache(
    pool: asyncpg.Pool,
    domain_id: str,
    language: str = "ru",
) -> str | None:
    """Build health profile and return summary text (cache-compatible wrapper).

    Returns the summary_text string or None if profile is empty.
    """
    result = await build_health_profile(pool, domain_id, language)
    text = result.get("summary_text", "")
    return text if text else None
