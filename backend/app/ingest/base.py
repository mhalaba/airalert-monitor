"""Baza fetcherow: retry z backoffem, rate-limit, health-check, anti-spoofing.

Zasady:
- wylacznie legalne kanaly (RSS/HTML publiczne strony instytucji, webhooki, manual),
- zadnego scrapingu naruszajacego regulaminy platform,
- surowa kopia odpowiedzi zawsze trafia do raw_messages (audyt).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

log = logging.getLogger("airalert.ingest")

MAX_RETRIES = 3
BACKOFF_BASE_S = 2.0
TIMEOUT_S = 15.0
USER_AGENT = "AirAlertMonitor/0.1 (+public-data-monitoring; contact: operator@example.org)"


@dataclass
class FetchedItem:
    external_id: str
    url: str | None
    title: str
    text: str
    published_at: dt.datetime | None
    raw_payload: dict


class FetchError(Exception):
    pass


class DomainMismatch(FetchError):
    """Ochrona przed spoofingiem: tresc spoza oczekiwanej domeny zrodla."""


def check_domain(url: str | None, domain_pin: str) -> None:
    if not url or not domain_pin:
        return
    host = urlparse(url).netloc.lower()
    if not (host == domain_pin or host.endswith("." + domain_pin)):
        raise DomainMismatch(f"URL {url} poza oczekiwaną domeną {domain_pin}")


async def get_with_retry(client: httpx.AsyncClient, url: str) -> httpx.Response:
    delay = BACKOFF_BASE_S
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(url, timeout=TIMEOUT_S)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001 - logujemy kazdy blad sieciowy
            last_exc = exc
            log.warning("Fetch %s nieudany (%s/%s): %s", url, attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)
                delay *= 2
    raise FetchError(f"Źródło niedostępne po {MAX_RETRIES} próbach: {last_exc}")


class RateLimiter:
    """Prosty token-bucket na minute per zrodlo."""

    def __init__(self, per_minute: int):
        self.per_minute = max(1, per_minute)
        self._window_start = 0.0
        self._count = 0

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            if now - self._window_start >= 60.0:
                self._window_start, self._count = now, 0
            if self._count < self.per_minute:
                self._count += 1
                return
            await asyncio.sleep(max(0.5, 60.0 - (now - self._window_start)))


async def parse_rss(xml_text: str) -> list[FetchedItem]:
    """Parse RSS/Atom przez feedparser (w oddzielnym watku - biblioteka jest sync)."""
    import feedparser

    def _parse() -> list[FetchedItem]:
        feed = feedparser.parse(xml_text)
        items: list[FetchedItem] = []
        for e in getattr(feed, "entries", [])[:50]:
            link = e.get("link")
            title = e.get("title", "")
            summary = e.get("summary", "") or e.get("description", "")
            published = e.get("published_parsed") or e.get("updated_parsed")
            pub_dt = (
                dt.datetime(*published[:6], tzinfo=dt.timezone.utc) if published else None
            )
            items.append(
                FetchedItem(
                    external_id=e.get("id") or link or f"{title}-{pub_dt}",
                    url=link,
                    title=title,
                    text=summary,
                    published_at=pub_dt,
                    raw_payload={"title": title, "summary": summary, "link": link},
                )
            )
        return items

    return await asyncio.to_thread(_parse)
