"""Price monitor agent — core search and watchlist logic."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from duckduckgo_search import DDGS

logger = structlog.get_logger()

# Category → search query suffix mapping (configurable via DB later)
_CATEGORY_SUFFIXES: dict[str, str] = {
    "medication": "купить аптека цена",
    "supplement": "купить БАД цена",
    "lab_test": "сдать анализ цена",
}


def _build_search_query(query: str, city: str, category: str | None) -> str:
    suffix = _CATEGORY_SUFFIXES.get(category or "", "купить цена")
    return f"{query} {city} {suffix}"


def _parse_price_from_snippet(snippet: str) -> Decimal | None:
    """Try to extract a numeric price from a search snippet.

    Looks for patterns like '1 400 ₽', '1400 руб', '1400.00' etc.
    """
    import re

    # Remove non-breaking spaces, thin spaces
    cleaned = snippet.replace("\xa0", " ").replace("\u2009", " ")

    # Pattern: digits (possibly with spaces/dots as thousand separators) followed by currency marker
    patterns = [
        r"(\d[\d\s.,]*)\s*(?:₽|руб|р\.)",
        r"(?:от|цена|стоимость|за)\s*(\d[\d\s.,]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            # Remove thousand separators (spaces), keep last dot/comma as decimal
            raw = raw.replace(" ", "")
            # Handle comma as decimal separator
            if "," in raw and "." not in raw:
                raw = raw.replace(",", ".")
            elif "," in raw and "." in raw:
                raw = raw.replace(",", "")
            try:
                value = Decimal(raw)
                if value > 0:
                    return value
            except Exception:
                continue
    return None


def _extract_source_name(url: str) -> str:
    """Extract a human-readable source name from a URL."""
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
        # Remove 'www.' prefix
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return "unknown"


def _search_sync(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Run synchronous DuckDuckGo search."""
    with DDGS() as ddgs:
        return list(ddgs.text(query, region="ru-ru", max_results=max_results))


async def search_prices(
    pool: asyncpg.Pool,
    query: str,
    city: str,
    category: str,
) -> list[dict[str, Any]]:
    """Search prices for a product across sources.

    Calls web search, parses results, saves snapshots to price_snapshot,
    returns results sorted by price ascending.
    """
    search_query = _build_search_query(query, city, category)

    try:
        raw_results = await asyncio.to_thread(_search_sync, search_query)
    except Exception as exc:
        await logger.awarning(
            "price_search_failed", query=query, city=city, error=str(exc)
        )
        return []

    results: list[dict[str, Any]] = []

    for r in raw_results:
        snippet = r.get("body", "")
        url = r.get("href", "")
        price = _parse_price_from_snippet(snippet)
        if price is None:
            continue

        source = _extract_source_name(url)
        results.append(
            {
                "product_name": query,
                "source": source,
                "price": float(price),
                "pharmacy_name": r.get("title", ""),
                "url": url,
                "city": city,
            }
        )

    results.sort(key=lambda x: x["price"])

    # Save snapshots to DB
    if results:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO price_snapshot (product_name, source, city, price, pharmacy_name, url)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                [
                    (
                        row["product_name"],
                        row["source"],
                        row["city"],
                        Decimal(str(row["price"])),
                        row["pharmacy_name"],
                        row["url"],
                    )
                    for row in results
                ],
            )

    await logger.ainfo(
        "price_search_completed",
        query=query,
        city=city,
        category=category,
        results_count=len(results),
    )

    return results


async def monitor_watchlist(
    pool: asyncpg.Pool,
    domain_id: str,
) -> dict[str, Any]:
    """Check prices for all items in a user's watchlist.

    For each item, runs search_prices, updates best_price/best_source/best_url/last_checked_at.
    Returns summary: {checked: N, price_drops: N, items: [...]}.
    """
    uid = UUID(domain_id)

    async with pool.acquire() as conn:
        # Load agent config to get city
        config_row = await conn.fetchrow(
            "SELECT settings FROM agent_config WHERE domain_id = $1 AND agent_code = $2",
            uid,
            "price_monitor",
        )
        city = "Москва"
        if config_row and config_row["settings"]:
            import json

            settings = (
                json.loads(config_row["settings"])
                if isinstance(config_row["settings"], str)
                else config_row["settings"]
            )
            city = settings.get("city", city)

        watchlist = await conn.fetch(
            "SELECT id, product_name, product_category, best_price FROM price_watchlist WHERE domain_id = $1",
            uid,
        )

    if not watchlist:
        return {"checked": 0, "price_drops": 0, "items": []}

    checked = 0
    price_drops = 0
    items: list[dict[str, Any]] = []

    for row in watchlist:
        results = await search_prices(
            pool,
            query=row["product_name"],
            city=city,
            category=row["product_category"],
        )

        checked += 1
        old_best = row["best_price"]

        if results:
            best = results[0]  # sorted by price asc
            new_best = Decimal(str(best["price"]))

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE price_watchlist
                    SET best_price = $1, best_source = $2, best_url = $3, last_checked_at = now()
                    WHERE id = $4
                    """,
                    new_best,
                    best["source"],
                    best["url"],
                    row["id"],
                )

            dropped = old_best is not None and new_best < old_best
            if dropped:
                price_drops += 1

            items.append(
                {
                    "product_name": row["product_name"],
                    "best_price": float(new_best),
                    "best_source": best["source"],
                    "best_url": best["url"],
                    "price_dropped": dropped,
                    "old_price": float(old_best) if old_best else None,
                }
            )
        else:
            # Update last_checked_at even if no results
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE price_watchlist SET last_checked_at = now() WHERE id = $1",
                    row["id"],
                )
            items.append(
                {
                    "product_name": row["product_name"],
                    "best_price": float(old_best) if old_best else None,
                    "best_source": None,
                    "best_url": None,
                    "price_dropped": False,
                    "old_price": float(old_best) if old_best else None,
                }
            )

    await logger.ainfo(
        "watchlist_monitored",
        domain_id=domain_id,
        checked=checked,
        price_drops=price_drops,
    )

    return {"checked": checked, "price_drops": price_drops, "items": items}


async def check_thresholds(
    pool: asyncpg.Pool,
    domain_id: str,
) -> list[dict[str, Any]]:
    """Compare watchlist target_price vs best_price.

    Returns items where best_price <= target_price (threshold met).
    """
    uid = UUID(domain_id)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, product_name, product_category, target_price, best_price,
                   best_source, best_url, last_checked_at
            FROM price_watchlist
            WHERE domain_id = $1
              AND target_price IS NOT NULL
              AND best_price IS NOT NULL
              AND best_price <= target_price
            """,
            uid,
        )

    result = [
        {
            "id": str(row["id"]),
            "product_name": row["product_name"],
            "product_category": row["product_category"],
            "target_price": float(row["target_price"]),
            "best_price": float(row["best_price"]),
            "best_source": row["best_source"],
            "best_url": row["best_url"],
            "last_checked_at": (
                row["last_checked_at"].isoformat() if row["last_checked_at"] else None
            ),
        }
        for row in rows
    ]

    await logger.ainfo(
        "thresholds_checked",
        domain_id=domain_id,
        threshold_met_count=len(result),
    )

    return result
