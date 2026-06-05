"""Rate limiting for all Rossum API traffic.

Rossum throttles clients to 10 requests/second globally and answers excess
with HTTP 429 + a ``Retry-After`` header. The bundled SDK retries 429 blindly
(exponential backoff, ignoring Retry-After) and applies no proactive limit, so
a big load or the concurrent reference-data fetch can hammer the API.

``RateLimitedTransport`` is an httpx transport wrapper that (a) caps the send
rate with a sliding-window token bucket shared by all concurrent tasks and
(b) on 429 waits the server-mandated time and retries before handing the
response back (the SDK's own retry stays as the outer fallback). ``install``
swaps it into the SDK client's single internal httpx client, so every request
— including SDK-internal pagination — flows through it.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

import httpx

# Fixed by design (no user-facing knob): headroom under Rossum's 10 req/s.
MAX_REQUESTS_PER_SECOND = 8
# 429 retries per request before giving up and returning the response.
MAX_RETRIES_429 = 5
# Upper bound for a single Retry-After/backoff wait.
MAX_WAIT_SECONDS = 60.0


class RateLimitedTransport(httpx.AsyncBaseTransport):
    """httpx transport wrapper: token-bucket throttle + Retry-After-aware 429 retry."""

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport | None = None,
        rate: int = MAX_REQUESTS_PER_SECOND,
        max_retries: int = MAX_RETRIES_429,
    ):
        self._inner = inner or httpx.AsyncHTTPTransport()
        self._rate = rate
        self._max_retries = max_retries
        self._sends: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def _throttle(self) -> None:
        """Block until a send slot is free in the rolling 1-second window."""
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._sends and now - self._sends[0] >= 1.0:
                    self._sends.popleft()
                if len(self._sends) < self._rate:
                    self._sends.append(now)
                    return
                wait = 1.0 - (now - self._sends[0])
            await asyncio.sleep(max(wait, 0.001))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await self._throttle()
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def install(client):
    """Route ALL of an ``AsyncRossumAPIClient``'s traffic through the limiter.

    Replaces the SDK's single internal ``httpx.AsyncClient`` (the documented-
    by-test contract ``client._http_client.client``) with one carrying a
    ``RateLimitedTransport``, preserving the configured timeout. Returns the
    same client for call-site convenience.
    """
    internal = client._http_client
    old = internal.client
    internal.client = httpx.AsyncClient(
        timeout=old.timeout, transport=RateLimitedTransport()
    )
    return client
