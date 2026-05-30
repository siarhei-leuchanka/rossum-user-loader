from rossum_user_loader.web import launcher
from tests.conftest import FakeClient, FakeGroup, FakeQueue


def test_free_port_returns_int():
    port = launcher._free_port()
    assert isinstance(port, int) and port > 0


def test_make_state_builds_reference_and_working_loader():
    groups = [FakeGroup("annotator", "https://x/groups/1")]
    queues = [FakeQueue(123, "https://x/queues/123", "Q1")]
    client = FakeClient()

    state = launcher.make_state("https://x/org/1", client, [], groups, queues)

    assert state.roles == [{"name": "annotator", "url": "https://x/groups/1"}]
    assert state.queues == [{"id": 123, "name": "Q1", "url": "https://x/queues/123"}]
    assert state.secret  # non-empty session token

    records = state.loader([{
        "auth_type": "password", "email": "n@x.io", "first_name": "N", "last_name": "X",
        "username": "newuser", "oidc_id": "", "role": "annotator",
        "queue_ids": "123", "can_approve": "no",
    }])
    assert any("User created" in m["Messages"] for m in records)
    assert client.created and client.created[0]["username"] == "newuser"
