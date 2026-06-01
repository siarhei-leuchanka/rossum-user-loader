"""Back-end side of the web UI: owns the API client and token, pre-fetches
reference data, and serves the Flask app. This module is intentionally the only
part of the web flow that touches Rossum — the ``web.app`` package never does.
"""

from __future__ import annotations

import asyncio
import secrets
import socket
import sys
import threading
import webbrowser

from rossum_user_loader import core
from rossum_user_loader.web.app import AppState, create_app


class Backend:
    """Owns the Rossum client + token and runs ALL API work on its own event
    loop in a dedicated thread.

    The Flask layer never imports ``rossum_api``, never sees the token, and never
    makes the HTTP call itself: it only hands row lists to ``run_load`` and gets
    back log records. Each call is dispatched onto this thread's loop and the
    caller (a Flask request thread) blocks for the result. Because there is a
    single long-lived loop, one client is created and reused across loads.
    """

    def __init__(self, conn: dict):
        self._conn = conn
        self._client = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _call(self, coro):
        # Dispatch a coroutine onto the back-end loop and block for its result.
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _client_on_loop(self):
        if self._client is None:
            from rossum_api import AsyncRossumAPIClient
            from rossum_api.dtos import Token

            self._client = AsyncRossumAPIClient(
                base_url=self._conn["domain"],
                credentials=Token(token=self._conn["token"]),
            )
        return self._client

    def collect_data(self):
        async def _go():
            return await core.collect_data(await self._client_on_loop())

        return self._call(_go())

    def run_load(self, rows, organization, org_groups, org_queues, existing_users) -> list[dict]:
        async def _go():
            client = await self._client_on_loop()
            logger = await core.run_load(
                client, rows, organization, org_groups, org_queues, existing_users
            )
            return logger.get()

        return self._call(_go())


def _free_port() -> int:
    # Ask the OS for a free port, then release it. There is a small TOCTOU
    # window before Flask rebinds it; acceptable for a local single-user tool.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _with_assignments(user, group_name_by_url, queue_name_by_url) -> dict:
    """Add human-readable ``role_names``/``queue_names`` to an existing-user
    record by resolving its group/queue URLs against the org reference data.
    Unresolvable URLs fall back to the raw value so nothing is silently lost."""
    enriched = dict(user)
    enriched["role_names"] = [group_name_by_url.get(g, g) for g in user.get("groups", [])]
    enriched["queue_names"] = [queue_name_by_url.get(q, q) for q in user.get("queues", [])]
    return enriched


def make_state(organization, backend, active_users, org_groups, org_queues) -> AppState:
    """Build the AppState the Flask layer renders.

    ``loader`` simply hands the rows to ``backend.run_load``, which executes the
    API work on the back-end thread/loop. The web layer never touches Rossum or
    the token — it only calls this in-process handoff and blocks for the result.
    """
    roles = [{"name": g.name, "url": g.url} for g in org_groups]
    queues = [{"id": q.id, "name": q.name, "url": q.url} for q in org_queues]

    group_name_by_url = {g.url: g.name for g in org_groups}
    queue_name_by_url = {q.url: q.name for q in org_queues}
    existing = [
        _with_assignments(u, group_name_by_url, queue_name_by_url) for u in active_users
    ]

    def loader(rows: list[dict]) -> list[dict]:
        return backend.run_load(rows, organization, org_groups, org_queues, active_users)

    return AppState(
        secret=secrets.token_urlsafe(32),
        roles=roles,
        queues=queues,
        existing_users=existing,
        loader=loader,
    )


def launch() -> None:
    """Prompt for connection details, start the back-end, and serve locally."""
    from rossum_user_loader.cli import gather_connection

    conn = gather_connection()

    # The back-end thread owns the client/token and makes every Rossum call.
    backend = Backend(conn)
    try:
        active_users, org_groups, org_queues = backend.collect_data()
    except Exception as exc:  # noqa: BLE001
        # Bad token / wrong domain / no network: report clearly and exit instead
        # of dumping an httpx/SDK traceback.
        print(f"\nERROR: {core.connection_error_message(exc)}", file=sys.stderr)
        raise SystemExit(1) from None

    state = make_state(
        conn["organization"], backend, active_users, org_groups, org_queues
    )
    app = create_app(state)
    port = _free_port()
    url = f"http://127.0.0.1:{port}/?key={state.secret}"

    print(f"\nUser Loader web UI running. Open this URL in your browser:\n  {url}\n")
    print(
        "(The ?key=... above is a local session key for THIS run only — "
        "it is NOT your Rossum API token, which never leaves this process.)\n"
    )
    print("Press Ctrl-C to stop.\n")
    webbrowser.open(url)
    app.run(host="127.0.0.1", port=port)
