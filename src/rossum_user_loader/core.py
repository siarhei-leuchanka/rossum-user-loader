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

from rossum_api import AsyncRossumAPIClient

# Columns the loader understands in an input row. The values double as the
# scaffold for the payload built per user.
SUPPORTED_COLUMNS = {
    "auth_type": "",
    "email": "",
    "first_name": "",
    "last_name": "",
    "oidc_id": "",
    "role": "",
    "queue_ids": "",
    "can_approve": "",
}


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
    payload["username"] = row.get("email", "")
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
                    "email": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
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
