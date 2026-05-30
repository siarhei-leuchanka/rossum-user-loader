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
    # Ask the OS for a free port, then release it. There is a small TOCTOU
    # window before Flask rebinds it; acceptable for a local single-user tool.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def make_state(organization, client_factory, active_users, org_groups, org_queues) -> AppState:
    """Build the AppState the Flask layer renders. The injected ``loader``
    closes over the client factory/org so the web package never sees the token.

    ``client_factory`` is a zero-arg callable returning a fresh API client. Each
    load runs via ``asyncio.run`` (a new event loop per call) and a new client is
    created INSIDE that loop, because an async HTTP client binds to the loop it is
    first used on. Reusing one client across ``asyncio.run`` calls would fail with
    "Event loop is closed".
    """
    roles = [{"name": g.name, "url": g.url} for g in org_groups]
    queues = [{"id": q.id, "name": q.name, "url": q.url} for q in org_queues]

    def loader(rows: list[dict]) -> list[dict]:
        async def _go():
            client = client_factory()
            return await core.run_load(
                client, rows, organization, org_groups, org_queues, active_users
            )

        return asyncio.run(_go()).get()

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

    def client_factory():
        return AsyncRossumAPIClient(
            base_url=conn["domain"], credentials=Token(token=conn["token"])
        )

    # Fetch reference data with a client created inside this run's event loop.
    async def _collect():
        return await core.collect_data(client_factory())

    active_users, org_groups, org_queues = asyncio.run(_collect())

    state = make_state(
        conn["organization"], client_factory, active_users, org_groups, org_queues
    )
    app = create_app(state)
    port = _free_port()
    url = f"http://127.0.0.1:{port}/?token={state.secret}"

    print(f"\nUser Loader web UI running. Open this URL in your browser:\n  {url}\n")
    print("Press Ctrl-C to stop.\n")
    webbrowser.open(url)
    app.run(host="127.0.0.1", port=port)
