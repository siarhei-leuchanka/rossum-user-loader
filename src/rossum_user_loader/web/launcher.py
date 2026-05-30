"""Back-end side of the web UI: owns the API client and token, pre-fetches
reference data, and serves the Flask app. This module is intentionally the only
part of the web flow that touches Rossum — the ``web.app`` package never does.
"""

from __future__ import annotations

import asyncio
import secrets
import socket
import webbrowser

from rossum_user_loader import core
from rossum_user_loader.web.app import AppState, create_app


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def make_state(organization, client, active_users, org_groups, org_queues) -> AppState:
    """Build the AppState the Flask layer renders. The injected ``loader``
    closes over the client/org so the web package never sees the token."""
    roles = [{"name": g.name, "url": g.url} for g in org_groups]
    queues = [{"id": q.id, "name": q.name, "url": q.url} for q in org_queues]

    def loader(rows: list[dict]) -> list[dict]:
        logger = asyncio.run(
            core.run_load(client, rows, organization, org_groups, org_queues, active_users)
        )
        return logger.get()

    return AppState(
        secret=secrets.token_urlsafe(32),
        roles=roles,
        queues=queues,
        existing_users=active_users,
        loader=loader,
    )


def launch() -> None:
    """Prompt for connection details, fetch reference data, and serve locally."""
    from rossum_api import AsyncRossumAPIClient
    from rossum_api.dtos import Token

    from rossum_user_loader.cli import gather_connection

    conn = gather_connection()
    client = AsyncRossumAPIClient(
        base_url=conn["domain"], credentials=Token(token=conn["token"])
    )
    active_users, org_groups, org_queues = asyncio.run(core.collect_data(client))

    state = make_state(conn["organization"], client, active_users, org_groups, org_queues)
    app = create_app(state)
    port = _free_port()
    url = f"http://127.0.0.1:{port}/?token={state.secret}"

    print(f"\nUser Loader web UI running. Open this URL in your browser:\n  {url}\n")
    print("Press Ctrl-C to stop.\n")
    webbrowser.open(url)
    app.run(host="127.0.0.1", port=port)
