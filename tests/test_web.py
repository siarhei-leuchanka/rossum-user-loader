import pytest

from rossum_user_loader.web.app import AppState, create_app


def make_state(loader=None):
    return AppState(
        secret="s3cr3t",
        roles=[{"name": "annotator", "url": "https://x/groups/1"}],
        queues=[{"id": 123, "name": "Q1", "url": "https://x/queues/123"}],
        existing_users=[
            {
                "username": "u1", "email": "u1@x.io", "first_name": "U", "last_name": "One",
                "role_names": ["editor"], "queue_names": ["Invoices"],
            }
        ],
        loader=loader
        or (lambda rows: [
            {"Messages": "User created", "username": r.get("username", "")} for r in rows
        ]),
    )


@pytest.fixture
def client():
    app = create_app(make_state())
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_forbidden_without_token(client):
    assert client.get("/").status_code == 403


def test_index_ok_with_token(client):
    resp = client.get("/?key=s3cr3t")
    assert resp.status_code == 200
    assert b"Start Load" in resp.data


def test_template_download_requires_session(client):
    assert client.get("/template.csv").status_code == 403


def test_template_download_after_auth(client):
    client.get("/?key=s3cr3t")
    resp = client.get("/template.csv")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/csv")
    assert b"username" in resp.data


def test_load_invokes_loader_and_returns_summary(client):
    client.get("/?key=s3cr3t")  # authenticate (sets session cookie)
    resp = client.post("/load", json={"rows": [{"username": "newuser", "email": "n@x.io"}]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["summary"]["created"] == 1
    assert any(r["username"] == "newuser" for r in data["records"])


def test_load_requires_session(client):
    resp = client.post("/load", json={"rows": []})
    assert resp.status_code == 403


def test_log_csv_404_before_any_load(client):
    client.get("/?key=s3cr3t")
    assert client.get("/log.csv").status_code == 404


def test_log_csv_after_load(client):
    client.get("/?key=s3cr3t")
    client.post("/load", json={"rows": [{"username": "newuser", "email": "n@x.io"}]})
    resp = client.get("/log.csv")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/csv")
    assert b"Messages" in resp.data


def test_index_contains_grid_and_controls(client):
    html = client.get("/?key=s3cr3t").data
    for marker in (b'id="grid"', b'id="paste"', b"Clear", b"Download template", b"Start Load"):
        assert marker in html
    assert b"annotator" in html
    assert b"Q1" in html


def test_load_returns_500_when_loader_raises():
    def boom(rows):
        raise RuntimeError("kaboom")
    app = create_app(make_state(loader=boom))
    app.config.update(TESTING=True)
    c = app.test_client()
    c.get("/?key=s3cr3t")
    resp = c.post("/load", json={"rows": [{"username": "x"}]})
    assert resp.status_code == 500
    assert "kaboom" in resp.get_json()["error"]


def test_summary_total_reconciles_with_buckets():
    # A password user emits "User created" + "Password reset"; total must not
    # double-count the reset record.
    records = [
        {"Messages": "User created - {}"},
        {"Messages": "Password reset - {}"},
        {"Messages": "Skipped-User Exists"},
        {"Messages": "Error - user not created - boom"},
    ]
    from rossum_user_loader.web.app import _summarize
    s = _summarize(records)
    assert s == {"total": 3, "created": 1, "skipped": 1, "errors": 1}


def test_index_includes_dedup_machinery(client):
    html = client.get("/?key=s3cr3t").data
    assert b'id="dupwarn"' in html
    assert b"EXISTING_USERNAMES" in html
    assert b"u1" in html  # existing username embedded for the client-side check


def test_existing_tab_shows_roles_and_queues(client):
    html = client.get("/?key=s3cr3t").data
    # Distinctive values only present on the existing user (not in ROLES/QUEUES).
    assert b"editor" in html
    assert b"Invoices" in html
    assert b"roles" in html and b"queues" in html  # column headers
