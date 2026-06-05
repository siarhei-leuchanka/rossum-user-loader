"""Tests for the rate-limited httpx transport."""

import asyncio
import time

import httpx
import pytest

from rossum_user_loader import ratelimit


class RecordingTransport(httpx.AsyncBaseTransport):
    """Inner transport stub: records send times, returns scripted responses.

    ``script`` is a list of (status_code, headers) tuples consumed per request;
    when exhausted, returns 200 with no headers.
    """

    def __init__(self, script=None):
        self.times: list[float] = []
        self.script = list(script or [])

    async def handle_async_request(self, request) -> httpx.Response:
        self.times.append(time.monotonic())
        status, headers = self.script.pop(0) if self.script else (200, {})
        return httpx.Response(status, headers=headers, json={}, request=request)


def _client(transport: ratelimit.RateLimitedTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport, base_url="https://x.test")


def test_throttle_caps_requests_per_rolling_second():
    inner = RecordingTransport()
    transport = ratelimit.RateLimitedTransport(inner=inner, rate=4)

    async def go():
        async with _client(transport) as c:
            await asyncio.gather(*(c.get("/u") for _ in range(10)))

    asyncio.run(go())

    times = sorted(inner.times)
    assert len(times) == 10
    # No rolling 1-second window may contain more than `rate` sends.
    for i in range(len(times)):
        in_window = [t for t in times if times[i] <= t < times[i] + 1.0]
        assert len(in_window) <= 4, f"window starting at send {i} holds {len(in_window)} sends"
    # 10 requests at 4/s must take at least 2 seconds overall.
    assert times[-1] - times[0] >= 2.0 - 0.05


def test_429_respects_retry_after_then_succeeds():
    inner = RecordingTransport(script=[
        (429, {"Retry-After": "1"}),
        (429, {"Retry-After": "1"}),
        (200, {}),
    ])
    transport = ratelimit.RateLimitedTransport(inner=inner, rate=100)

    async def go():
        async with _client(transport) as c:
            return await c.get("/u")

    start = time.monotonic()
    resp = asyncio.run(go())
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert len(inner.times) == 3            # original + 2 retries
    assert elapsed >= 2.0 - 0.05            # waited Retry-After twice


def test_429_without_retry_after_uses_backoff():
    inner = RecordingTransport(script=[(429, {}), (200, {})])
    transport = ratelimit.RateLimitedTransport(inner=inner, rate=100)

    async def go():
        async with _client(transport) as c:
            return await c.get("/u")

    start = time.monotonic()
    resp = asyncio.run(go())
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert len(inner.times) == 2
    assert elapsed >= 1.0 - 0.05            # first backoff step is 1 s


def test_429_budget_exhausted_returns_last_response():
    inner = RecordingTransport(script=[(429, {"Retry-After": "0"})] * 10)
    transport = ratelimit.RateLimitedTransport(inner=inner, rate=100, max_retries=2)

    async def go():
        async with _client(transport) as c:
            return await c.get("/u")

    resp = asyncio.run(go())
    assert resp.status_code == 429          # surfaced to the SDK's own retry/error path
    assert len(inner.times) == 3            # original + max_retries
