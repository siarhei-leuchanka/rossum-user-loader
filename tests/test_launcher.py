from rossum_user_loader.web import launcher
from tests.conftest import FakeClient, FakeGroup, FakeQueue


def test_free_port_returns_int():
    port = launcher._free_port()
    assert isinstance(port, int) and port > 0


def _sample_row(**over):
    base = {
        "auth_type": "password", "email": "n@x.io", "first_name": "N", "last_name": "X",
        "username": "newuser", "oidc_id": "", "role": "annotator",
        "queue_ids": "123", "can_approve": "no",
    }
    base.update(over)
    return base


def test_make_state_builds_reference_and_working_loader():
    groups = [FakeGroup("annotator", "https://x/groups/1")]
    queues = [FakeQueue(123, "https://x/queues/123", "Q1")]
    client = FakeClient()

    state = launcher.make_state("https://x/org/1", lambda: client, [], groups, queues)

    assert state.roles == [{"name": "annotator", "url": "https://x/groups/1"}]
    assert state.queues == [{"id": 123, "name": "Q1", "url": "https://x/queues/123"}]
    assert state.secret  # non-empty session token

    records = state.loader([_sample_row()])
    assert any("User created" in m["Messages"] for m in records)
    assert client.created and client.created[0]["username"] == "newuser"


def test_loader_can_run_twice_fresh_client_per_call():
    # Regression: the loader must work on repeated calls (each uses its own
    # asyncio.run/event loop). A new client is built per call via the factory,
    # so there is no client bound to an already-closed loop.
    groups = [FakeGroup("annotator", "https://x/groups/1")]
    queues = [FakeQueue(123, "https://x/queues/123", "Q1")]
    built = []

    def factory():
        c = FakeClient()
        built.append(c)
        return c

    state = launcher.make_state("https://x/org/1", factory, [], groups, queues)

    state.loader([_sample_row(username="u1", email="u1@x.io")])
    state.loader([_sample_row(username="u2", email="u2@x.io")])

    assert len(built) == 2  # a fresh client per load
    assert built[0].created[0]["username"] == "u1"
    assert built[1].created[0]["username"] == "u2"
