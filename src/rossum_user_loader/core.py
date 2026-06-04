"""User-loading logic for Rossum, independent of any I/O front end.

Functions here take plain Python values (dict rows, a configured client) and
return data or raise ``ValueError`` on bad input. They do not prompt, and they
do not read or write files. The CLI (and, later, the Flask UI) supply the
inputs and decide how to report results.
"""

from __future__ import annotations

import asyncio
import copy
import datetime
from enum import Enum

import httpx

from rossum_api import AsyncRossumAPIClient
from rossum_api.dtos import Token

# Columns the loader understands in an input row. The values double as the
# scaffold for the payload built per user.
SUPPORTED_COLUMNS = {
    "auth_type": "",
    "email": "",
    "first_name": "",
    "last_name": "",
    "username": "",
    "oidc_id": "",
    "role": "",
    "queue_ids": "",
    "can_approve": "",
}

# Columns that MUST be present in an input file. `username` is optional (it
# defaults to the email), so legacy templates without it still load.
REQUIRED_COLUMNS = (
    "auth_type",
    "email",
    "first_name",
    "last_name",
    "oidc_id",
    "role",
    "queue_ids",
    "can_approve",
)


class _ResourceHotFix(Enum):
    # The SDK lacks a password-reset helper; we hit the endpoint directly.
    RESET_PASSWORD = "auth/password/reset"


def get_supported_columns() -> dict:
    return copy.deepcopy(SUPPORTED_COLUMNS)


def prepare_user_data(row: dict, organization: str, org_groups: list, org_queues: list) -> dict:
    """Build a create-user payload from one input row.

    ``row`` is a mapping of column name -> stripped string value.
    Raises ``ValueError`` if the requested role/approver group is missing.
    """
    payload = get_supported_columns()

    payload["oidc_id"] = row.get("oidc_id") or row.get("email", "")
    payload["auth_type"] = row.get("auth_type", "")
    payload["username"] = row.get("username") or row.get("email", "")
    payload["email"] = row.get("email", "")
    payload["first_name"] = row.get("first_name", "")
    payload["last_name"] = row.get("last_name", "")
    payload["organization"] = organization

    group_url_by_name = {group.name: group.url for group in org_groups}
    admin_group_url = group_url_by_name.get("admin", "")
    approver_group_url = group_url_by_name.get("approver")

    groups: list[str] = []

    requested_role = row.get("role", "")
    role_url = group_url_by_name.get(requested_role)
    if role_url is None:
        raise ValueError(
            f"Role '{requested_role}' not found among organization groups "
            f"{sorted(group_url_by_name)}"
        )
    groups.append(role_url)

    if row.get("can_approve") == "yes":
        if approver_group_url is None:
            raise ValueError(
                "can_approve is 'yes' but no 'approver' group exists in the organization"
            )
        if approver_group_url not in groups:
            groups.append(approver_group_url)

    payload["groups"] = groups

    queues: list[str] = []
    if admin_group_url not in groups:
        requested_queue_ids = str(row.get("queue_ids", "")).split("\n")
        for queue in org_queues:
            if str(queue.id) in requested_queue_ids:
                queues.append(queue.url)
    payload["queues"] = queues

    # Drop the input-only columns that are not part of the API payload.
    for key in ("role", "queue_ids", "can_approve"):
        payload.pop(key, None)

    return payload


async def list_active_users(client: AsyncRossumAPIClient) -> list[dict]:
    actual_users = []
    async for user in client.list_users():
        if user.deleted is False:
            actual_users.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "auth_type": user.auth_type,
                    "oidc_id": user.oidc_id,
                    "groups": user.groups,
                    "queues": user.queues,
                }
            )
    return actual_users


async def list_groups(client: AsyncRossumAPIClient) -> list:
    return [group async for group in client.list_user_roles()]


async def list_all_queues(client: AsyncRossumAPIClient) -> list:
    return [queue async for queue in client.list_queues()]


async def collect_data(client: AsyncRossumAPIClient):
    """Fetch existing users, groups, and queues concurrently."""
    return await asyncio.gather(
        list_active_users(client),
        list_groups(client),
        list_all_queues(client),
    )


async def create_user(client: AsyncRossumAPIClient, user_data: dict):
    """Create a single user. Returns the API response."""
    return await client.create_new_user(user_data)


async def reset_password(client: AsyncRossumAPIClient, email: str):
    """Trigger a password-reset email (works around a missing SDK method)."""
    return await client._http_client.create(
        _ResourceHotFix.RESET_PASSWORD, {"email": email}
    )


async def patch_user(client: AsyncRossumAPIClient, user_id: int, payload: dict):
    """Update (PATCH) an existing user. Returns the API response.

    The SDK has no first-class user-update helper, so we use the internal HTTP
    client's generic update against the User resource (same mechanism as the
    password-reset hot-fix above)."""
    from rossum_api.models import Resource

    return await client._http_client.update(Resource.User, user_id, payload)


def _emit(on_result, level: str, message: str) -> None:
    if on_result is not None:
        on_result(level, message)


async def _patch_one(client, user_data, existing_by_username, logger, on_result) -> None:
    """Patch an existing user matched by username.

    Updated fields: first_name, last_name, oidc_id, auth_type, groups, queues.
    Identity fields (username, email, organization) are never patched.
    """
    key = user_data["username"].lower().strip()
    existing = existing_by_username.get(key)
    if not existing or not existing.get("id"):
        _emit(on_result, "error", f"Cannot patch - no existing user '{user_data['username']}'")
        logger.add("Error - patch failed - no existing user", **user_data)
        return

    if user_data["auth_type"] not in ("sso", "password"):
        _emit(
            on_result, "skip",
            f"Check user data entry - {user_data['username']} (invalid auth_type for patch)",
        )
        logger.add("Error-check user data entry. Invalid auth_type for patch.", **user_data)
        return

    patch_payload = {
        "first_name": user_data["first_name"],
        "last_name": user_data["last_name"],
        "oidc_id": user_data["oidc_id"],
        "auth_type": user_data["auth_type"],
        "groups": user_data["groups"],
        "queues": user_data["queues"],
    }
    _emit(on_result, "info", f"Patching User: {user_data['username']}")
    try:
        response = await patch_user(client, existing["id"], patch_payload)
        logger.add(f"User patched - {response}", **user_data)
        _emit(on_result, "ok", f"User patched - {user_data['username']}")
    except Exception as exc:  # noqa: BLE001
        logger.add(f"Error - user not patched - {exc}", **user_data)
        _emit(on_result, "error", f"ERROR - user not patched - {exc}")


async def run_load(
    client: AsyncRossumAPIClient,
    rows: list[dict],
    organization: str,
    org_groups: list,
    org_queues: list,
    existing_users: list[dict],
    on_result=None,
) -> "Logger":
    """Create or patch each row's user (per-row ``action``), keyed by username.

    ``row["action"]`` is ``"create"`` (default) or ``"patch"``. Create skips a
    row whose username already exists; patch updates the matching existing user
    (roles, queues, names). Continues past per-user failures, recording every
    outcome in the returned Logger. ``on_result(level, message)`` — if given — is
    called per event for live console output; the web layer omits it. Callers
    pass the final rows (any template example row is dropped before calling).
    """
    logger = Logger()
    existing_by_username = {
        (u.get("username") or "").lower().strip(): u for u in existing_users
    }

    for row in rows:
        action = (row.get("action") or "create").strip().lower()
        try:
            user_data = prepare_user_data(row, organization, org_groups, org_queues)
        except ValueError as exc:
            _emit(on_result, "skip", f"Skipping row - {exc}")
            logger.add(f"Error - invalid user data - {exc}", email=row.get("email", ""))
            continue

        if action == "patch":
            await _patch_one(client, user_data, existing_by_username, logger, on_result)
            continue

        if user_data["auth_type"] not in ("sso", "password") or not user_data["email"]:
            _emit(on_result, "skip", f"Check user data entry - {user_data['email']}")
            logger.add("Error-check user data entry. No required fields.", **user_data)
            continue

        if user_data["username"].lower().strip() in existing_by_username:
            _emit(
                on_result,
                "skip",
                f"User Exists - {user_data['username']} "
                "(set this row's action to 'patch' to update the existing user)",
            )
            logger.add("Skipped-User Exists", **user_data)
            continue

        _emit(on_result, "info", f"Creating User: {user_data['email']}")
        try:
            response = await create_user(client, user_data)
            logger.add(f"User created - {response}", **user_data)
            _emit(on_result, "ok", f"User created - {user_data['email']}")
        except Exception as exc:  # noqa: BLE001
            logger.add(f"Error - user not created - {exc}", **user_data)
            _emit(on_result, "error", f"ERROR - user not created - {exc}")
            continue

        if user_data["auth_type"] == "password":
            try:
                response = await reset_password(client, user_data["email"])
                logger.add(f"Password reset - {response}", **user_data)
                _emit(on_result, "ok", f"Password reset for {user_data['email']}")
            except Exception as exc:  # noqa: BLE001
                logger.add(f"Error - password reset failed - {exc}", **user_data)
                _emit(on_result, "error", f"Password reset failed - {exc}")

    return logger


class Logger:
    """Accumulates structured log records for export."""

    def __init__(self):
        self.log: list[dict] = []

    def add(self, note, **kwargs):
        message = {"Messages": note, "timestamp": datetime.datetime.now()}
        message.update(kwargs)
        self.log.append(message)

    def get(self) -> list[dict]:
        return self.log


def summarize(records: list[dict]) -> dict:
    """Count outcomes from a list of log records by their message prefix.

    ``total`` reconciles with created+patched+skipped+errors; password-reset
    bookkeeping records are excluded from the error count (the user itself was
    already created and counted)."""
    def msg(r):
        return str(r.get("Messages", ""))

    created = sum(1 for r in records if msg(r).startswith("User created"))
    patched = sum(1 for r in records if msg(r).startswith("User patched"))
    skipped = sum(1 for r in records if "Skipped" in msg(r) or "Skipping" in msg(r))
    errors = sum(
        1
        for r in records
        if msg(r).startswith("Error") and "password reset" not in msg(r).lower()
    )
    return {
        "total": created + patched + skipped + errors,
        "created": created,
        "patched": patched,
        "skipped": skipped,
        "errors": errors,
    }


def generate_token(domain: str, username: str, password: str) -> str:
    """Exchange username + password for an API token via ``POST {domain}/auth/login``.

    ``domain`` is the base URL ending in ``/v1`` (e.g. https://x.rossum.app/api/v1).
    Returns the ``key`` from the response; raises on HTTP/connection errors.
    """
    response = httpx.post(
        f"{domain}/auth/login",
        json={"username": username, "password": password},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["key"]


def verify_credentials(domain: str, token: str) -> None:
    """Confirm a token actually authenticates against Rossum by making one real,
    authenticated request through the SDK — the same client/auth path the load
    uses. Raises on failure (invalid/expired token, wrong domain, no network).
    Lists users (which the loader needs anyway) and stops after the first item.
    """
    async def _run():
        client = AsyncRossumAPIClient(base_url=domain, credentials=Token(token=token))
        async for _user in client.list_users():
            break

    asyncio.run(_run())


def connection_error_message(exc: Exception) -> str:
    """A human-readable message for a failure to reach/authenticate with Rossum.

    Covers the common causes (wrong token, wrong/typo'd domain URL, no network)
    without leaking a raw stack trace; the original error is appended as detail.
    """
    return (
        "Could not connect to Rossum. Please check that your API token is correct, "
        "the domain URL is valid (e.g. https://<org>.rossum.app/api/v1), and that you "
        f"have a working network connection.\nDetails: {exc}"
    )
