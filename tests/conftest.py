"""Shared fakes for the rossum_user_loader test suite."""

from dataclasses import dataclass


@dataclass
class FakeGroup:
    name: str
    url: str


@dataclass
class FakeQueue:
    id: int
    url: str
    name: str = ""


class FakeHttpClient:
    """Captures password-reset (create) and user-patch (update) calls."""

    def __init__(self):
        self.reset_calls = []
        self.update_calls = []

    async def create(self, resource, payload):
        self.reset_calls.append((resource, payload))
        return {"status": "reset-sent"}

    async def update(self, resource, id_, data):
        self.update_calls.append((resource, id_, data))
        return {"id": id_, **data}


class FakeClient:
    """Minimal stand-in for AsyncRossumAPIClient used by core.run_load."""

    def __init__(self, fail_emails=None):
        self._http_client = FakeHttpClient()
        self.created = []
        self._fail_emails = set(fail_emails or [])

    async def create_new_user(self, user_data):
        if user_data["email"] in self._fail_emails:
            raise RuntimeError("boom")
        self.created.append(user_data)
        return {"id": 999, "username": user_data["username"]}
