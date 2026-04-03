"""Scraper for vapteke.ru pharmacy aggregator.

Parses search results from vapteke.ru HTML pages.
Falls back to SearXNG if vapteke.ru is unreachable or returns no results.
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

# City name (lowercase) → vapteke region slug.
# vapteke.ru uses region subdomains or path-based city selection.
_CITY_SLUG: dict[str, str] = {
    "москва": "moskva",
    "санкт-петербург": "sankt-peterburg",
    "петербург": "sankt-peterburg",
    "спб": "sankt-peterburg",
    "новосибирск": "novosibirsk",
    "екатеринбург": "ekaterinburg",
    "казань": "kazan",
    "нижний новгород": "nizhnij-novgorod",
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
    "махачкала": "makhachkala",
    "томск": "tomsk",
    "оренбург": "orenburg",
    "кемерово": "kemerovo",
    "рязань": "ryazan",
    "астрахань": "astrakhan",
    "набережные челны": "naberezhnye-chelny",
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
                  AND source = 'vapteke'
                  AND checked_at > now() - interval '4 hours'
                ORDER BY price ASC
                """,
                f"%{query}%",
                city,
            )
        if rows:
            return [
                {
                    "product_name": r["product_name"],
                    "price": float(r["price"]),
                    "pharmacy_name": r["pharmacy_name"] or "",
                    "url": r["url"] or "",
                    "availability": True,
                }
                for r in rows
            ]
    except Exception as exc:
        await logger.awarning("vapteke_cache_check_failed", error=str(exc))
    return None


async def _save_to_cache(
    pool: Any, results: list[dict[str, Any]], query: str, city: str
) -> None:
    """Persist results into price_snapshot."""
    if pool is None or not results:
        return
    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO price_snapshot (product_name, source, city, price, pharmacy_name, url)
                VALUES ($1, 'vapteke', $2, $3, $4, $5)
                """,
                [
                    (
                        r["product_name"],
                        city,
                        Decimal(str(r["price"])),
                        r.get("pharmacy_name", ""),
                        r.get("url", ""),
                    )
                    for r in results
                ],
            )
    except Exception as exc:
        await logger.awarning("vapteke_cache_save_failed", error=str(exc))


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


def _parse_vapteke_html(html: str) -> list[dict[str, Any]]:
    """Parse product listings from vapteke.ru search HTML.

    Vapteke uses server-rendered HTML with product cards containing
    title, price, pharmacy info, and availability.
    """
    results: list[dict[str, Any]] = []

    # Pattern for product cards — vapteke renders items in divs/cards
    # with product name, price, and link info
    product_blocks = re.findall(
        r'<div[^>]*class="[^"]*(?:product-card|catalog-item|search-result)[^"]*"[^>]*>(.*?)</div>\s*</div>',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    if not product_blocks:
        # Try broader pattern for any structured product listing
        product_blocks = re.findall(
            r'<(?:div|li|article)[^>]*class="[^"]*(?:item|product|result)[^"]*"[^>]*>(.*?)</(?:div|li|article)>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

    for block in product_blocks:
        # Extract product name from link or heading
        name_match = re.search(
            r'<a[^>]*>([^<]+)</a>|<h[2-4][^>]*>([^<]+)</h[2-4]>',
            block,
            re.IGNORECASE,
        )
        if not name_match:
            continue
        name = (name_match.group(1) or name_match.group(2) or "").strip()
        if not name:
            continue

        # Extract URL
        url_match = re.search(r'href="(/[^"]+)"', block)
        product_url = f"https://vapteke.ru{url_match.group(1)}" if url_match else ""

        # Extract price
        price = _parse_price_from_text(block)
        if price is None:
            # Try dedicated price element
            price_match = re.search(
                r'class="[^"]*price[^"]*"[^>]*>([^<]+)',
                block,
                re.IGNORECASE,
            )
            if price_match:
                price = _parse_price_from_text(price_match.group(1))

        if price is None or price <= 0:
            continue

        # Extract pharmacy name if present
        pharmacy_match = re.search(
            r'class="[^"]*(?:pharmacy|apteka|seller)[^"]*"[^>]*>([^<]+)',
            block,
            re.IGNORECASE,
        )
        pharmacy_name = pharmacy_match.group(1).strip() if pharmacy_match else "vapteke.ru"

        results.append(
            {
                "product_name": name,
                "price": price,
                "pharmacy_name": pharmacy_name,
                "url": product_url,
                "availability": True,
            }
        )

    return results


async def _fetch_vapteke(query: str, city: str) -> list[dict[str, Any]]:
    """Fetch and parse vapteke.ru search results."""
    await _rate_limit()

    city_slug = _CITY_SLUG.get(city.lower().strip(), "moskva")
    url = f"https://vapteke.ru/{city_slug}/search/"

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(url, params={"q": query})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        await logger.awarning(
            "vapteke_fetch_failed", query=query, city=city, error=str(exc)
        )
        return []

    return _parse_vapteke_html(resp.text)


async def _fetch_searxng_fallback(query: str, city: str) -> list[dict[str, Any]]:
    """Fallback: query SearXNG for vapteke prices."""
    searxng_query = f"vapteke.ru {query} {city} цена"
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
        await logger.awarning("vapteke_searxng_fallback_failed", error=str(exc))
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("results", []):
        item_url = item.get("url", "")
        if "vapteke.ru" not in item_url:
            continue

        title = item.get("title", "")
        snippet = item.get("content", "")

        price = _parse_price_from_text(snippet) or _parse_price_from_text(title)
        if price is None:
            continue

        results.append(
            {
                "product_name": title,
                "price": price,
                "pharmacy_name": "vapteke.ru",
                "url": item_url,
                "availability": True,
            }
        )

    return results


async def search_vapteke(
    query: str,
    city: str,
    pool: Any = None,
) -> list[dict[str, Any]]:
    """Search vapteke.ru for product prices.

    Args:
        query: Product name to search for.
        city: City name in Russian (e.g. "Москва", "Санкт-Петербург").
        pool: Optional asyncpg pool for caching via price_snapshot table.

    Returns:
        List of dicts with keys: product_name, price, pharmacy_name, url, availability.
        Returns empty list on failure.
    """
    # Check cache first
    cached = await _check_cache(pool, query, city)
    if cached:
        await logger.ainfo(
            "vapteke_cache_hit", query=query, city=city, count=len(cached)
        )
        return cached

    # Try direct vapteke.ru scraping
    results = await _fetch_vapteke(query, city)

    # Fallback to SearXNG if no results
    if not results:
        await logger.ainfo("vapteke_no_results_trying_searxng", query=query, city=city)
        results = await _fetch_searxng_fallback(query, city)

    # Sort by price ascending
    results.sort(key=lambda x: x["price"])

    # Save to cache
    if results:
        await _save_to_cache(pool, results, query, city)

    await logger.ainfo(
        "vapteke_search_completed",
        query=query,
        city=city,
        count=len(results),
        source="vapteke" if results else "none",
    )

    return results
