"""Scraper for uteka.ru pharmacy aggregator.

Parses SSR-embedded Nuxt payload (pinia.productList) from search pages.
Falls back to SearXNG if Uteka is unreachable or returns no results.
"""

from __future__ import annotations

import asyncio
import json
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

# City name (lowercase) → uteka subdomain.
# uteka.ru without subdomain defaults to Moscow.
_CITY_SUBDOMAIN: dict[str, str] = {
    "москва": "",
    "санкт-петербург": "spb",
    "петербург": "spb",
    "спб": "spb",
    "новосибирск": "novosibirsk",
    "екатеринбург": "ekaterinburg",
    "казань": "kazan",
    "нижний новгород": "nn",
    "красноярск": "krasnoyarsk",
    "челябинск": "chelyabinsk",
    "самара": "samara",
    "уфа": "ufa",
    "ростов-на-дону": "rostov",
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
    "набережные челны": "nabchelny",
    "пенза": "penza",
    "липецк": "lipetsk",
    "тула": "tula",
    "киров": "kirov",
    "калининград": "kaliningrad",
}


def _build_url(query: str, city: str) -> str:
    """Build uteka search URL with city subdomain."""
    subdomain = _CITY_SUBDOMAIN.get(city.lower().strip(), "")
    host = f"{subdomain}.uteka.ru" if subdomain else "uteka.ru"
    return f"https://{host}/search/?query={httpx.URL('', params={'q': query}).params.get('q', query)}"


def _build_search_url(query: str, city: str) -> str:
    """Build uteka search URL with proper encoding."""
    subdomain = _CITY_SUBDOMAIN.get(city.lower().strip(), "")
    host = f"{subdomain}.uteka.ru" if subdomain else "uteka.ru"
    base = f"https://{host}/search/"
    return base, {"query": query}


def _deref(data: list, idx: Any, depth: int = 0) -> Any:
    """Dereference a Nuxt SSR payload index, unwrapping Ref/Reactive wrappers."""
    if depth > 10:
        return idx
    if isinstance(idx, int) and 0 <= idx < len(data):
        val = data[idx]
        if (
            isinstance(val, list)
            and len(val) == 2
            and isinstance(val[0], str)
            and val[0] in ("Ref", "Reactive", "ShallowReactive", "ShallowRef")
        ):
            return _deref(data, val[1], depth + 1)
        return val
    return idx


def _parse_nuxt_products(html: str) -> list[dict[str, Any]]:
    """Extract product list from Nuxt SSR payload embedded in HTML."""
    match = re.search(
        r'data-nuxt-data="nuxt-app"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return []

    # Navigate: data[1] -> pinia -> productList -> products
    try:
        root = data[1]
        pinia_dict = data[root["pinia"]]
        pl_dict = data[pinia_dict["productList"]]
        products_raw = _deref(data, pl_dict["products"])
    except (KeyError, IndexError, TypeError):
        return []

    if not isinstance(products_raw, list):
        return []

    results: list[dict[str, Any]] = []
    for p_ref in products_raw:
        p = _deref(data, p_ref)
        if not isinstance(p, dict):
            continue

        try:
            full_title = _deref(data, p.get("fullTitle", ""))
            min_price = _deref(data, p.get("minPrice"))
            alias = _deref(data, p.get("alias", ""))
            is_available = _deref(data, p.get("isAvailable", False))
            producer = _deref(data, p.get("fullProducer", ""))
            pharmacy_count = _deref(data, p.get("pharmacyCount", 0))

            if not full_title or min_price is None:
                continue

            price_val = float(min_price) if min_price else 0.0
            if price_val <= 0:
                continue

            # Build product URL from alias
            product_url = f"https://uteka.ru/product/{alias}/" if alias else ""

            results.append(
                {
                    "product_name": str(full_title),
                    "price": price_val,
                    "pharmacy_name": str(producer) if producer else "",
                    "url": product_url,
                    "availability": bool(is_available),
                    "pharmacy_count": int(pharmacy_count) if pharmacy_count else 0,
                }
            )
        except (TypeError, ValueError):
            continue

    return results


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
                  AND source = 'uteka'
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
        await logger.awarning("uteka_cache_check_failed", error=str(exc))
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
                VALUES ($1, 'uteka', $2, $3, $4, $5)
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
        await logger.awarning("uteka_cache_save_failed", error=str(exc))


async def _fetch_uteka(query: str, city: str) -> list[dict[str, Any]]:
    """Fetch and parse uteka.ru search results."""
    await _rate_limit()

    subdomain = _CITY_SUBDOMAIN.get(city.lower().strip(), "")
    host = f"{subdomain}.uteka.ru" if subdomain else "uteka.ru"
    url = f"https://{host}/search/"

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(url, params={"query": query})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        await logger.awarning(
            "uteka_fetch_failed", query=query, city=city, error=str(exc)
        )
        return []

    return _parse_nuxt_products(resp.text)


async def _fetch_searxng_fallback(query: str, city: str) -> list[dict[str, Any]]:
    """Fallback: query SearXNG for uteka prices."""
    searxng_query = f"uteka.ru {query} {city} цена"
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
        await logger.awarning("uteka_searxng_fallback_failed", error=str(exc))
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("results", []):
        item_url = item.get("url", "")
        if "uteka.ru" not in item_url:
            continue

        title = item.get("title", "")
        snippet = item.get("content", "")

        # Try to extract price from snippet
        price = _parse_price_from_text(snippet) or _parse_price_from_text(title)
        if price is None:
            continue

        results.append(
            {
                "product_name": title,
                "price": price,
                "pharmacy_name": "uteka.ru",
                "url": item_url,
                "availability": True,
            }
        )

    return results


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


async def search_uteka(
    query: str,
    city: str,
    pool: Any = None,
) -> list[dict[str, Any]]:
    """Search uteka.ru for product prices.

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
            "uteka_cache_hit", query=query, city=city, count=len(cached)
        )
        return cached

    # Try direct uteka.ru scraping
    results = await _fetch_uteka(query, city)

    # Fallback to SearXNG if no results
    if not results:
        await logger.ainfo("uteka_no_results_trying_searxng", query=query, city=city)
        results = await _fetch_searxng_fallback(query, city)

    # Sort by price ascending
    results.sort(key=lambda x: x["price"])

    # Save to cache
    if results:
        await _save_to_cache(pool, results, query, city)

    await logger.ainfo(
        "uteka_search_completed",
        query=query,
        city=city,
        count=len(results),
        source="uteka" if results else "none",
    )

    return results
