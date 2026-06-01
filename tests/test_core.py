from rossum_user_loader import core
from tests.conftest import FakeGroup, FakeQueue

GROUPS = [
    FakeGroup("annotator", "https://x/groups/1"),
    FakeGroup("approver", "https://x/groups/2"),
    FakeGroup("admin", "https://x/groups/3"),
]
QUEUES = [FakeQueue(123, "https://x/queues/123")]


def _row(**over):
    base = {
        "auth_type": "password", "email": "a@b.c", "first_name": "A",
        "last_name": "B", "oidc_id": "", "role": "annotator",
        "queue_ids": "123", "can_approve": "no", "username": "",
    }
    base.update(over)
    return base


def test_username_defaults_to_email_when_blank():
    payload = core.prepare_user_data(_row(username=""), "https://x/org/1", GROUPS, QUEUES)
    assert payload["username"] == "a@b.c"


def test_username_used_when_present():
    payload = core.prepare_user_data(_row(username="custom"), "https://x/org/1", GROUPS, QUEUES)
    assert payload["username"] == "custom"


def test_required_columns_excludes_username():
    assert "username" not in core.REQUIRED_COLUMNS
    assert "email" in core.REQUIRED_COLUMNS


class _FakeUser:
    def __init__(self, username, email):
        self.id = 1
        self.username = username
        self.email = email
        self.first_name = "F"
        self.last_name = "L"
        self.groups = []
        self.queues = []
        self.deleted = False


class _UserClient:
    def __init__(self, users):
        self._users = users

    async def list_users(self):
        for u in self._users:
            yield u


async def test_list_active_users_has_username_and_email():
    client = _UserClient([_FakeUser("jdoe", "j@x.io")])
    users = await core.list_active_users(client)
    assert users[0]["username"] == "jdoe"
    assert users[0]["email"] == "j@x.io"


from tests.conftest import FakeClient


async def test_run_load_creates_new_and_skips_existing_by_username():
    rows = [
        _row(email="new@x.io", username="newuser", auth_type="password"),
        _row(email="dup@x.io", username="dupuser", auth_type="password"),
    ]
    existing = [{"username": "dupuser", "email": "dup@x.io"}]
    client = FakeClient()

    logger = await core.run_load(
        client, rows, "https://x/org/1", GROUPS, QUEUES, existing
    )

    # only the non-duplicate user was created
    assert [u["username"] for u in client.created] == ["newuser"]
    # password users get a reset request
    assert client._http_client.reset_calls
    notes = [m["Messages"] for m in logger.get()]
    assert any("User created" in n for n in notes)
    assert any("User Exists" in n for n in notes)


async def test_run_load_records_creation_failure_and_continues():
    rows = [
        _row(email="boom@x.io", username="boom", auth_type="password"),
        _row(email="ok@x.io", username="ok", auth_type="password"),
    ]
    client = FakeClient(fail_emails={"boom@x.io"})

    logger = await core.run_load(client, rows, "https://x/org/1", GROUPS, QUEUES, [])

    assert [u["username"] for u in client.created] == ["ok"]
    notes = [m["Messages"] for m in logger.get()]
    assert any("Error - user not created" in n for n in notes)


async def test_run_load_invokes_on_result_callback():
    events = []
    rows = [_row(email="new@x.io", username="newuser", auth_type="password")]
    client = FakeClient()

    await core.run_load(
        client, rows, "https://x/org/1", GROUPS, QUEUES, [],
        on_result=lambda level, message: events.append((level, message)),
    )

    levels = [level for level, _ in events]
    assert "info" in levels   # "Creating User"
    assert "ok" in levels     # "User created" and "Password reset"


async def test_run_load_patches_existing_user_when_action_patch():
    rows = [_row(email="dup@x.io", username="dupuser", auth_type="password", action="patch")]
    existing = [{"username": "dupuser", "email": "dup@x.io", "id": 42}]
    client = FakeClient()

    logger = await core.run_load(client, rows, "https://x/org/1", GROUPS, QUEUES, existing)

    # patched via _http_client.update, not created
    assert client.created == []
    assert client._http_client.update_calls
    _resource, user_id, payload = client._http_client.update_calls[0]
    assert user_id == 42
    assert set(payload.keys()) == {"first_name", "last_name", "groups", "queues"}
    assert any("User patched" in m["Messages"] for m in logger.get())


async def test_run_load_patch_without_existing_user_records_error():
    rows = [_row(email="ghost@x.io", username="ghost", auth_type="password", action="patch")]
    client = FakeClient()

    logger = await core.run_load(client, rows, "https://x/org/1", GROUPS, QUEUES, [])

    assert client._http_client.update_calls == []
    assert client.created == []
    assert any("patch failed - no existing user" in m["Messages"] for m in logger.get())


def test_summarize_counts_outcomes():
    recs = [
        {"Messages": "User created - x"},
        {"Messages": "Password reset - x"},
        {"Messages": "User patched - y"},
        {"Messages": "Skipped-User Exists"},
        {"Messages": "Error - user not created - boom"},
    ]
    assert core.summarize(recs) == {
        "total": 4, "created": 1, "patched": 1, "skipped": 1, "errors": 1
    }


def test_connection_error_message_is_meaningful():
    msg = core.connection_error_message(RuntimeError("[Errno 8] nodename nor servname provided"))
    assert "Could not connect to Rossum" in msg
    assert "API token" in msg and "domain URL" in msg
    assert "nodename nor servname" in msg  # original detail preserved


def test_generate_token_posts_to_auth_login(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"key": "TKN123"}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(core.httpx, "post", fake_post)
    tok = core.generate_token("https://x.rossum.app/api/v1", "u@x.io", "pw")
    assert tok == "TKN123"
    assert captured["url"] == "https://x.rossum.app/api/v1/auth/login"
    assert captured["json"] == {"username": "u@x.io", "password": "pw"}


def test_verify_credentials_makes_authenticated_call(monkeypatch):
    seen = {}

    class _FakeClient:
        def __init__(self, base_url=None, credentials=None):
            seen["base_url"] = base_url
            seen["credentials"] = credentials

        async def list_users(self):
            seen["called"] = True
            return
            yield  # marks this an async generator (unreachable)

    monkeypatch.setattr(core, "AsyncRossumAPIClient", _FakeClient)
    core.verify_credentials("https://x.rossum.app/api/v1", "TKN")
    assert seen["called"] is True
    assert seen["base_url"] == "https://x.rossum.app/api/v1"
    assert seen["credentials"].token == "TKN"
