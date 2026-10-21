"""Deterministic checks on URLs an agent wants to cite: was it really retrieved, and is it live?"""

import asyncio
import ipaddress
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar
from urllib.parse import urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

CheckLive = Callable[[str], Awaitable[bool]]
_LIVE_CHECK_TIMEOUT = 5.0
_LIVE_CHECK_PARALLEL = 5
_BOT_BLOCKED = (401, 403, 429)


class _HasUrl(Protocol):
    url: str


S = TypeVar("S", bound=_HasUrl)


def normalize_url(url: str) -> str:
    """Scheme/host case, fragment and trailing slash do not make two URLs different."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def _is_public_http_url(url: str) -> bool:
    """Agents may be steered by web content, so never probe non-http(s) or local/private addresses."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme not in ("http", "https") or not host or host == "localhost" or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # a domain name
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


async def default_check_live(url: str) -> bool:
    """HEAD, then GET when HEAD is refused. Live means the page exists: 2xx/3xx, or
    401/403/429, which is how many official docs sites answer a script (they
    block bots but the page is there). 404/410/5xx and connection errors are dead."""
    if not _is_public_http_url(url):
        logger.warning("live check refused for non-public or non-http url %s", url)
        return False
    try:
        async with httpx.AsyncClient(timeout=_LIVE_CHECK_TIMEOUT, follow_redirects=True) as client:
            response = await client.head(url)
            if response.status_code >= 400:
                response = await client.get(url)
            return response.status_code < 400 or response.status_code in _BOT_BLOCKED
    except httpx.HTTPError:
        return False


async def keep_verified_sources(
    sources: list[S], fetched_urls: tuple[str, ...] | None, check_live: CheckLive = default_check_live
) -> list[S]:
    """Keeps only sources whose URL the session really retrieved (skipped when
    that could not be determined, `fetched_urls is None`) and that are live."""
    candidates = sources
    if fetched_urls is not None:
        fetched = {normalize_url(u) for u in fetched_urls}
        candidates = [s for s in sources if normalize_url(s.url) in fetched]
        dropped = len(sources) - len(candidates)
        if dropped:
            logger.warning("dropped %d cited url(s) the agent never retrieved", dropped)

    gate = asyncio.Semaphore(_LIVE_CHECK_PARALLEL)

    async def live(url: str) -> bool:
        async with gate:
            try:
                return await check_live(url)
            except Exception:
                logger.exception("live check crashed for %s; treating it as dead", url)
                return False

    verdicts = await asyncio.gather(*(live(s.url) for s in candidates))
    kept = [s for s, ok in zip(candidates, verdicts) if ok]
    if len(kept) < len(candidates):
        logger.warning("dropped %d cited url(s) that failed the live check", len(candidates) - len(kept))
    return kept
