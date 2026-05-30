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
