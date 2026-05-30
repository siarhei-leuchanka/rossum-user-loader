"""Flask presentation layer for the user loader.

This package is pure presentation: it imports nothing from ``rossum_api``,
holds no API token, and makes no API calls. The back-end injects an
``AppState`` carrying pre-fetched reference data and a ``loader(rows)`` callable
that runs the actual load. Every request is gated behind a per-session secret
token delivered in the launch URL.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Callable

from flask import Flask, Response, jsonify, render_template, request, send_file, session

from rossum_user_loader import csvio


@dataclass
class AppState:
    secret: str
    roles: list[dict]
    queues: list[dict]
    existing_users: list[dict]
    loader: Callable[[list[dict]], list[dict]]
    last_log: list[dict] = field(default_factory=list)


def _summarize(records: list[dict]) -> dict:
    def msg(r):
        return str(r.get("Messages", ""))

    created = sum(1 for r in records if msg(r).startswith("User created"))
    skipped = sum(1 for r in records if "Skipped" in msg(r) or "Skipping" in msg(r))
    # Exclude password-reset bookkeeping (success OR failure) from the headline
    # error count — the user itself was already created/counted.
    errors = sum(
        1
        for r in records
        if msg(r).startswith("Error") and "password reset" not in msg(r).lower()
    )
    # total reconciles with the three buckets (password-reset records are
    # bookkeeping, still present in the full records list and the CSV log).
    return {
        "total": created + skipped + errors,
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


def _jsonable(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        out.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()})
    return out


def create_app(state: AppState) -> Flask:
    app = Flask(__name__, template_folder="templates")
    app.secret_key = state.secret
    # Local session key gating browser access for this run. NOT a Rossum token.
    app.config["SESSION_KEY"] = state.secret

    @app.before_request
    def _gate():
        if request.endpoint == "static":
            return None
        if session.get("authed"):
            return None
        if (
            request.method == "GET"
            and request.path == "/"
            and request.args.get("key") == app.config["SESSION_KEY"]
        ):
            session["authed"] = True
            return None
        return ("Forbidden", 403)

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            roles=state.roles,
            queues=state.queues,
            existing=state.existing_users,
        )

    @app.get("/template.csv")
    def template_csv():
        return send_file(
            csvio.template_path(),
            mimetype="text/csv",
            as_attachment=True,
            download_name="user_load_template.csv",
        )

    @app.post("/load")
    def load():
        payload = request.get_json(force=True, silent=True) or {}
        rows = payload.get("rows", [])
        try:
            records = state.loader(rows)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500
        state.last_log = records
        return jsonify({"summary": _summarize(records), "records": _jsonable(records)})

    @app.get("/log.csv")
    def log_csv():
        if not state.last_log:
            return ("No log yet", 404)
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = csvio.write_log(os.path.join(tmp_dir, "user_load_log"), state.last_log)
            with open(path, "rb") as fh:
                data = fh.read()
        return Response(
            data,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=user_load_log.csv"},
        )

    return app
