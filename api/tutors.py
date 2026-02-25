import asyncio
import logging
from datetime import datetime
import requests

from config import TUTORS_API_URL, UAE_TZ

log = logging.getLogger("chessflow-bot")

def fetch_tutors(limit: int = 50) -> list[dict]:
    r = requests.get(TUTORS_API_URL, params={"limit": limit}, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("items", []) or []

async def get_tutors_cached(context, limit: int = 50) -> list[dict]:
    """
    60s cache in bot_data.
    """
    now = datetime.now(UAE_TZ)
    cache_ts = context.application.bot_data.get("tutors_cache_ts")
    cache_items = context.application.bot_data.get("tutors_cache_items")

    if cache_ts and cache_items and (now - cache_ts).total_seconds() < 60:
        return cache_items

    items = await asyncio.to_thread(fetch_tutors, limit)
    context.application.bot_data["tutors_cache_ts"] = now
    context.application.bot_data["tutors_cache_items"] = items
    return items