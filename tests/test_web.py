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
                "auth_type": "sso", "role_names": ["editor"], "queue_names": ["Invoices"],
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
    for marker in (b'id="grid"', b'id="paste"', b"Clear", b"Download CSV template", b"Start Load"):
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
        {"Messages": "User patched - {}"},
        {"Messages": "Skipped-User Exists"},
        {"Messages": "Error - user not created - boom"},
    ]
    from rossum_user_loader.web.app import _summarize
    s = _summarize(records)
    assert s == {"total": 4, "created": 1, "patched": 1, "skipped": 1, "errors": 1}


def test_index_includes_dedup_machinery(client):
    html = client.get("/?key=s3cr3t").data
    assert b'id="dupwarn"' in html
    assert b"EXISTING_USERNAMES" in html
    assert b"u1" in html  # existing username embedded for the client-side check


def test_existing_tab_shows_roles_queues_and_auth_type(client):
    html = client.get("/?key=s3cr3t").data
    # Distinctive values only present on the existing user (not in ROLES/QUEUES).
    assert b"editor" in html
    assert b"Invoices" in html
    assert b"roles" in html and b"queues" in html  # column headers
    # auth_type rendered as a cell (the JS option list has 'sso' only inside
    # <script>, so a literal <td>sso</td> can only come from the existing table).
    assert b"<td>sso</td>" in html


def test_existing_tab_has_copy_and_action_controls(client):
    html = client.get("/?key=s3cr3t").data
    assert b"Copy selected to load list" in html   # checkbox-driven bulk copy
    assert b"copySelectedExisting(" in html
    assert b"toggleAllExisting(" in html           # select-all checkbox
    assert b'class="existing-select"' in html      # per-row selection checkbox
    assert b"copyAllExisting(" in html
    assert b"<th>action</th>" in html              # per-row create/patch column
    assert b"Set all actions" in html              # master dropdown
    assert b"const EXISTING =" in html             # full records embedded for copy


def test_load_summary_includes_patched_via_stub(client):
    # The default stub loader emits "User created"; ensure the summary key set
    # now includes patched so the page can render it.
    client.get("/?key=s3cr3t")
    resp = client.post("/load", json={"rows": [{"username": "x", "email": "x@y.z"}]})
    data = resp.get_json()
    assert "patched" in data["summary"]


def test_non_loopback_host_is_rejected(client):
    # Even with a valid key, a non-loopback Host (DNS-rebinding) is refused.
    resp = client.get("/?key=s3cr3t", headers={"Host": "evil.example.com"})
    assert resp.status_code == 403


def test_cross_site_origin_post_is_rejected(client):
    client.get("/?key=s3cr3t")  # authenticate
    resp = client.post("/load", json={"rows": []}, headers={"Origin": "http://evil.example.com"})
    assert resp.status_code == 403


def test_loopback_origin_post_is_allowed(client):
    client.get("/?key=s3cr3t")  # authenticate
    resp = client.post("/load", json={"rows": []}, headers={"Origin": "http://127.0.0.1:5000"})
    assert resp.status_code == 200


def test_index_has_csv_file_loader(client):
    html = client.get("/?key=s3cr3t").data
    assert b'type="file"' in html          # CSV file picker
    assert b"loadCsvFile(" in html
    assert b"parseDelimited(" in html       # quote-aware ';' parser
    assert b'const DELIM = \';\'' in html or b"const DELIM = ';'" in html


def test_index_has_in_list_duplicate_detection(client):
    html = client.get("/?key=s3cr3t").data
    assert b"share a username with another row" in html  # in-list dup banner text
    assert b"dupinlist" in html                           # row highlight class


def test_queue_widget_is_searchable_multiselect(client):
    html = client.get("/?key=s3cr3t").data
    assert b"queue-widget" in html      # searchable queue widget
    assert b"q-search" in html          # filter input
    assert b"search queues" in html     # placeholder
    assert b'type="checkbox"' in html   # checkboxes keep multi-select


def test_queue_widget_resolves_by_name_or_id_and_flags_unmatched(client):
    html = client.get("/?key=s3cr3t").data
    assert b"not found in this org" in html                     # unmatched feedback
    assert b".toLowerCase() === tok.toLowerCase()" in html      # name resolution
    assert b"q-unmatched" in html


def test_django_style_chrome_and_confirm(client):
    html = client.get("/?key=s3cr3t").data
    assert b"dj-header" in html          # dark header bar with nav
    assert b"breadcrumbs" in html        # Django-style breadcrumbs
    assert b"crumb-current" in html
    assert b'class="module"' in html     # card modules
    assert b"Data source" in html        # template + file load grouped together
    assert b"table-toolbar" in html      # controls attached to the table
    assert b"confirmAndStart(" in html   # Start Load re-asks
    assert b"window.confirm(" in html
    assert b"start-load" in html         # distinguished submit button


def test_load_rejects_too_many_rows(client):
    client.get("/?key=s3cr3t")
    big = [{"username": "u%d" % i} for i in range(1001)]
    resp = client.post("/load", json={"rows": big})
    assert resp.status_code == 400
    assert "Too many rows" in resp.get_json()["error"]


def test_load_rejects_bad_shape(client):
    client.get("/?key=s3cr3t")
    assert client.post("/load", json={"rows": "notalist"}).status_code == 400


def test_load_rejects_oversized_field(client):
    client.get("/?key=s3cr3t")
    resp = client.post("/load", json={"rows": [{"email": "x" * 2000}]})
    assert resp.status_code == 400


def test_index_hardening_markers(client):
    html = client.get("/?key=s3cr3t").data
    assert b'max="100"' in html                      # add-rows capped in the UI
    assert b"MAX_ADD_ROWS" in html
    assert b"MAX_CSV_BYTES" in html                  # csv upload size cap
    assert b"Please choose a .csv file" in html      # csv mime/extension check


def test_bulk_set_all_queues_controls_present(client):
    html = client.get("/?key=s3cr3t").data
    assert b"Set all queues" in html
    assert b"Apply queues to all rows" in html
    assert b"applyQueuesToAll(" in html
    assert b"buildBulkQueues(" in html


def test_patch_field_highlighting_machinery_present(client):
    html = client.get("/?key=s3cr3t").data
    assert b"PATCHED_COLS" in html          # list of fields a patch writes
    assert b"highlightPatchFields(" in html
    assert b"will-patch" in html            # cell highlight class + CSS
    assert b"Will be written to the existing user" in html
