import asyncio

from rossum_user_loader import core
from rossum_user_loader.web import launcher
from tests.conftest import FakeClient, FakeGroup, FakeQueue


def _sample_row(**over):
    base = {
        "auth_type": "password", "email": "n@x.io", "first_name": "N", "last_name": "X",
        "username": "newuser", "oidc_id": "", "role": "annotator",
        "queue_ids": "123", "can_approve": "no",
    }
    base.update(over)
    return base


class FakeBackend:
    """Stand-in for the real Backend: runs core.run_load with a FakeClient,
    no thread/loop/network. Lets us test the make_state handoff in isolation."""

    def __init__(self, collect_result=None):
        self.client = FakeClient()
        self.calls = 0
        self.collect_calls = 0
        self.collect_result = collect_result

    def run_load(self, rows, organization, org_groups, org_queues, existing_users):
        self.calls += 1
        logger = asyncio.run(
            core.run_load(self.client, rows, organization, org_groups, org_queues, existing_users)
        )
        return logger.get()

    def collect_data(self):
        self.collect_calls += 1
        return self.collect_result


def test_free_port_returns_int():
    port = launcher._free_port()
    assert isinstance(port, int) and port > 0


def test_make_state_builds_reference_and_hands_off_to_backend():
    groups = [FakeGroup("annotator", "https://x/groups/1")]
    queues = [FakeQueue(123, "https://x/queues/123", "Q1")]
    backend = FakeBackend()

    state = launcher.make_state("https://x/org/1", backend, [], groups, queues)

    assert state.roles == [{"name": "annotator", "url": "https://x/groups/1"}]
    assert state.queues == [{"id": 123, "name": "Q1", "url": "https://x/queues/123"}]
    assert state.secret  # non-empty session key

    records = state.loader([_sample_row()])
    assert any("User created" in m["Messages"] for m in records)
    assert backend.client.created and backend.client.created[0]["username"] == "newuser"


def test_loader_delegates_each_submission_to_backend():
    groups = [FakeGroup("annotator", "https://x/groups/1")]
    queues = [FakeQueue(123, "https://x/queues/123", "Q1")]
    backend = FakeBackend()

    state = launcher.make_state("https://x/org/1", backend, [], groups, queues)
    state.loader([_sample_row(username="u1", email="u1@x.io")])
    state.loader([_sample_row(username="u2", email="u2@x.io")])

    assert backend.calls == 2
    assert [u["username"] for u in backend.client.created] == ["u1", "u2"]


def test_backend_reuses_single_client_across_loads(monkeypatch):
    # The real Backend runs on a persistent loop in its own thread; a single
    # client is created once and reused. Two loads must both succeed (this is
    # the case that previously raised "Event loop is closed").
    backend = launcher.Backend({"domain": "https://x/api/v1", "token": "t"})
    fake = FakeClient()

    async def _fake_client():
        return fake

    monkeypatch.setattr(backend, "_client_on_loop", _fake_client)

    groups = [FakeGroup("annotator", "https://x/groups/1")]
    queues = [FakeQueue(123, "https://x/queues/123", "Q1")]

    r1 = backend.run_load([_sample_row(username="u1", email="u1@x.io")], "https://x/org/1", groups, queues, [])
    r2 = backend.run_load([_sample_row(username="u2", email="u2@x.io")], "https://x/org/1", groups, queues, [])

    assert any("User created" in m["Messages"] for m in r1)
    assert any("User created" in m["Messages"] for m in r2)
    assert [u["username"] for u in fake.created] == ["u1", "u2"]


def test_refresh_users_refetches_enriches_and_loader_sees_fresh_data():
    groups = [FakeGroup("annotator", "https://x/groups/1")]
    queues = [FakeQueue(123, "https://x/queues/123", "Q1")]
    fresh_user = {
        "username": "newuser", "email": "n@x.io", "first_name": "N", "last_name": "X",
        "groups": ["https://x/groups/1"], "queues": ["https://x/queues/123"],
    }
    backend = FakeBackend(collect_result=([fresh_user], groups, queues))

    # Launch with NO existing users — "newuser" appears only after the refetch.
    state = launcher.make_state("https://x/org/1", backend, [], groups, queues)

    refreshed = state.refresh_users()
    assert backend.collect_calls == 1
    # Returned records are enriched like the initial list (names, not URLs).
    assert refreshed[0]["username"] == "newuser"
    assert refreshed[0]["role_names"] == ["annotator"]
    assert refreshed[0]["queue_names"] == ["Q1"]

    # The loader's duplicate matching now uses the FRESH user list: a "create"
    # for newuser is skipped instead of creating a duplicate.
    records = state.loader([_sample_row()])
    assert any("Skipped" in m["Messages"] for m in records)
    assert not backend.client.created


def test_with_assignments_resolves_urls_to_names():
    groups = [FakeGroup("annotator", "https://x/groups/1")]
    queues = [FakeQueue(123, "https://x/queues/123", "Q1")]
    group_name_by_url = {g.url: g.name for g in groups}
    queue_name_by_url = {q.url: q.name for q in queues}

    user = {
        "username": "u1", "email": "u1@x.io", "first_name": "U", "last_name": "One",
        "groups": ["https://x/groups/1"], "queues": ["https://x/queues/123", "https://x/queues/999"],
    }
    enriched = launcher._with_assignments(user, group_name_by_url, queue_name_by_url)
    assert enriched["role_names"] == ["annotator"]
    # Unresolvable URL falls back to the raw value rather than being dropped.
    assert enriched["queue_names"] == ["Q1", "https://x/queues/999"]


def test_backend_client_is_rate_limited(monkeypatch):
    # The backend's lazily-created SDK client must be routed through the
    # rate limiter (ratelimit.install) before any API call is made.
    import asyncio as aio

    from rossum_api.dtos import Token

    from rossum_user_loader import ratelimit

    installed = []
    monkeypatch.setattr(ratelimit, "install", lambda c: installed.append(c) or c)

    backend = launcher.Backend({"domain": "https://x/api/v1", "credentials": Token(token="t")})
    try:
        client = aio.run(backend._client_on_loop())
    finally:
        backend._loop.call_soon_threadsafe(backend._loop.stop)
    assert installed == [client]


def test_launch_exits_cleanly_on_connection_failure(monkeypatch, capsys):
    # A bad token / domain must produce a clear message + clean exit, not a
    # raw httpx traceback.
    monkeypatch.setattr(
        "rossum_user_loader.cli.gather_connection",
        lambda: {"token": "t", "domain": "https://bad.example",
                 "organization": "https://bad.example/organizations/1"},
    )

    class BadBackend:
        def __init__(self, conn):
            pass

        def collect_data(self):
            raise RuntimeError("[Errno 8] nodename nor servname provided, or not known")

    monkeypatch.setattr(launcher, "Backend", BadBackend)

    import pytest
    with pytest.raises(SystemExit) as ei:
        launcher.launch()
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "Could not connect to Rossum" in err
