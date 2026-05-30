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

    def __init__(self):
        self.client = FakeClient()
        self.calls = 0

    def run_load(self, rows, organization, org_groups, org_queues, existing_users):
        self.calls += 1
        logger = asyncio.run(
            core.run_load(self.client, rows, organization, org_groups, org_queues, existing_users)
        )
        return logger.get()


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
