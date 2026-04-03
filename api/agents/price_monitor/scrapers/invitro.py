"""Scraper for invitro.ru lab test catalog.

Parses search results from invitro.ru/analizes/ pages.
Falls back to SearXNG if invitro.ru is unreachable or returns no results.
"""

from __future__ import annotations

import asyncio
import re
import time
from decimal import Decimal
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_RATE_LIMIT_INTERVAL = 2.0  # seconds between requests
_last_request_ts: float = 0.0

# City name (lowercase) → invitro city slug for URL.
# invitro.ru uses city subdomains or path-based selection.
_CITY_SLUG: dict[str, str] = {
    "москва": "moscow",
    "санкт-петербург": "spb",
    "петербург": "spb",
    "спб": "spb",
    "новосибирск": "novosibirsk",
    "екатеринбург": "ekaterinburg",
    "казань": "kazan",
    "нижний новгород": "nizhny-novgorod",
    "красноярск": "krasnoyarsk",
    "челябинск": "chelyabinsk",
    "самара": "samara",
    "уфа": "ufa",
    "ростов-на-дону": "rostov-na-donu",
    "краснодар": "krasnodar",
    "омск": "omsk",
    "воронеж": "voronezh",
    "пермь": "perm",
    "волгоград": "volgograd",
    "тюмень": "tyumen",
    "саратов": "saratov",
    "тольятти": "tolyatti",
    "ижевск": "izhevsk",
    "барнаул": "barnaul",
    "иркутск": "irkutsk",
    "хабаровск": "khabarovsk",
    "ярославль": "yaroslavl",
    "владивосток": "vladivostok",
    "томск": "tomsk",
    "оренбург": "orenburg",
    "кемерово": "kemerovo",
    "рязань": "ryazan",
    "астрахань": "astrakhan",
    "пенза": "penza",
    "липецк": "lipetsk",
    "тула": "tula",
    "киров": "kirov",
    "калининград": "kaliningrad",
}


async def _rate_limit() -> None:
    """Enforce minimum interval between requests."""
    global _last_request_ts
    now = time.monotonic()
    elapsed = now - _last_request_ts
    if elapsed < _RATE_LIMIT_INTERVAL:
        await asyncio.sleep(_RATE_LIMIT_INTERVAL - elapsed)
    _last_request_ts = time.monotonic()


async def _check_cache(pool: Any, query: str, city: str) -> list[dict[str, Any]] | None:
    """Return cached results from price_snapshot if fresh (< 4 hours)."""
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT product_name, price, pharmacy_name, url
                FROM price_snapshot
                WHERE product_name ILIKE $1
                  AND city = $2
                  AND source = 'invitro'
                  AND checked_at > now() - interval '4 hours'
                ORDER BY price ASC
                """,
                f"%{query}%",
                city,
            )
        if rows:
            return [
                {
                    "test_name": r["product_name"],
                    "price": float(r["price"]),
                    "lab_name": "Инвитро",
                    "url": r["url"] or "",
                    "turnaround_time": r["pharmacy_name"] or "",
                }
                for r in rows
            ]
    except Exception as exc:
        await logger.awarning("invitro_cache_check_failed", error=str(exc))
    return None


async def _save_to_cache(
    pool: Any, results: list[dict[str, Any]], query: str, city: str
) -> None:
    """Persist results into price_snapshot.

    Maps lab-test fields to price_snapshot columns:
      test_name → product_name, turnaround_time → pharmacy_name.
    """
    if pool is None or not results:
        return
    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO price_snapshot (product_name, source, city, price, pharmacy_name, url)
                VALUES ($1, 'invitro', $2, $3, $4, $5)
                """,
                [
                    (
                        r["test_name"],
                        city,
                        Decimal(str(r["price"])),
                        r.get("turnaround_time", ""),
                        r.get("url", ""),
                    )
                    for r in results
                ],
            )
    except Exception as exc:
        await logger.awarning("invitro_cache_save_failed", error=str(exc))


def _parse_price_from_text(text: str) -> float | None:
    """Extract a price value from text."""
    if not text:
        return None
    cleaned = text.replace("\xa0", " ").replace("\u2009", " ")
    patterns = [
        r"(?:от\s+)?(\d[\d\s]*(?:[.,]\d{1,2})?)\s*(?:₽|руб|р\.)",
        r"(?:цена|стоимость)\s*[:—–-]?\s*(\d[\d\s]*(?:[.,]\d{1,2})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            raw = match.group(1).strip().replace(" ", "")
            if "," in raw and "." not in raw:
                raw = raw.replace(",", ".")
            try:
                val = float(raw)
                if val > 0:
                    return val
            except ValueError:
                continue
    return None


def _parse_turnaround_from_text(text: str) -> str:
    """Extract turnaround time from text (e.g. '1 день', '2-3 дня')."""
    if not text:
        return ""
    patterns = [
        r"(\d+(?:\s*[-–]\s*\d+)?\s*(?:д(?:ень|ня|ней)|раб[.\s]*дн[а-я]*))",
        r"(\d+(?:\s*[-–]\s*\d+)?\s*(?:час[а-я]*))",
        r"(?:срок[а-я]*\s*[:—–-]?\s*)(\d+(?:\s*[-–]\s*\d+)?\s*(?:д[а-я]*|ч[а-я]*))",
        r"(?:готовность\s*[:—–-]?\s*)(\d+(?:\s*[-–]\s*\d+)?\s*(?:д[а-я]*|ч[а-я]*))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _parse_invitro_html(html: str) -> list[dict[str, Any]]:
    """Parse lab test listings from invitro.ru search HTML.

    Invitro renders test catalog items with test name, price,
    turnaround time, and links to individual test pages.
    """
    results: list[dict[str, Any]] = []

    # Invitro uses various class patterns for analysis cards
    product_blocks = re.findall(
        r'<div[^>]*class="[^"]*(?:analyzes-item|analysis-item|catalog-item|test-item|search-item)[^"]*"[^>]*>(.*?)</div>\s*(?:</div>|\s*<div)',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    if not product_blocks:
        # Broader pattern
        product_blocks = re.findall(
            r'<(?:div|li|article|tr)[^>]*class="[^"]*(?:item|result|analyz)[^"]*"[^>]*>(.*?)</(?:div|li|article|tr)>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

    for block in product_blocks:
        # Extract test name
        name_match = re.search(
            r'<a[^>]*href="(/analizes/[^"]*)"[^>]*>([^<]+)</a>'
            r'|<h[2-4][^>]*>([^<]+)</h[2-4]>'
            r'|class="[^"]*(?:name|title)[^"]*"[^>]*>([^<]+)<',
            block,
            re.IGNORECASE,
        )
        if not name_match:
            continue

        href = name_match.group(1) or ""
        name = (
            name_match.group(2)
            or name_match.group(3)
            or name_match.group(4)
            or ""
        ).strip()
        if not name:
            continue

        product_url = f"https://www.invitro.ru{href}" if href else ""

        # Extract price
        price = _parse_price_from_text(block)
        if price is None or price <= 0:
            continue

        # Extract turnaround time
        turnaround = _parse_turnaround_from_text(block)

        results.append(
            {
                "test_name": name,
                "price": price,
                "lab_name": "Инвитро",
                "url": product_url,
                "turnaround_time": turnaround,
            }
        )

    return results


async def _fetch_invitro(query: str, city: str) -> list[dict[str, Any]]:
    """Fetch and parse invitro.ru search results."""
    await _rate_limit()

    city_slug = _CITY_SLUG.get(city.lower().strip(), "moscow")
    url = f"https://www.invitro.ru/{city_slug}/analizes/for-doctors/"

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(url, params={"text": query})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        await logger.awarning(
            "invitro_fetch_failed", query=query, city=city, error=str(exc)
        )
        return []

    return _parse_invitro_html(resp.text)


async def _fetch_searxng_fallback(query: str, city: str) -> list[dict[str, Any]]:
    """Fallback: query SearXNG for invitro lab test prices."""
    searxng_query = f"invitro.ru {query} {city} цена анализ"
    try:
        async with httpx.AsyncClient(
            timeout=10.0, headers={"User-Agent": _USER_AGENT}
        ) as client:
            resp = await client.get(
                "http://localhost:8888/search",
                params={"q": searxng_query, "format": "json", "engines": "google"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        await logger.awarning("invitro_searxng_fallback_failed", error=str(exc))
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("results", []):
        item_url = item.get("url", "")
        if "invitro.ru" not in item_url:
            continue

        title = item.get("title", "")
        snippet = item.get("content", "")

        price = _parse_price_from_text(snippet) or _parse_price_from_text(title)
        if price is None:
            continue

        turnaround = (
            _parse_turnaround_from_text(snippet)
            or _parse_turnaround_from_text(title)
        )

        results.append(
            {
                "test_name": title,
                "price": price,
                "lab_name": "Инвитро",
                "url": item_url,
                "turnaround_time": turnaround,
            }
        )

    return results


async def search_invitro(
    query: str,
    city: str,
    pool: Any = None,
) -> list[dict[str, Any]]:
    """Search invitro.ru for lab test prices.

    Args:
        query: Lab test name to search for (e.g. "общий анализ крови").
        city: City name in Russian (e.g. "Москва", "Санкт-Петербург").
        pool: Optional asyncpg pool for caching via price_snapshot table.

    Returns:
        List of dicts with keys: test_name, price, lab_name, url, turnaround_time.
        Returns empty list on failure.
    """
    # Check cache first
    cached = await _check_cache(pool, query, city)
    if cached:
        await logger.ainfo(
            "invitro_cache_hit", query=query, city=city, count=len(cached)
        )
        return cached

    # Try direct invitro.ru scraping
    results = await _fetch_invitro(query, city)

    # Fallback to SearXNG if no results
    if not results:
        await logger.ainfo("invitro_no_results_trying_searxng", query=query, city=city)
        results = await _fetch_searxng_fallback(query, city)

    # Sort by price ascending
    results.sort(key=lambda x: x["price"])

    # Save to cache
    if results:
        await _save_to_cache(pool, results, query, city)

    await logger.ainfo(
        "invitro_search_completed",
        query=query,
        city=city,
        count=len(results),
        source="invitro" if results else "none",
    )

    return results
