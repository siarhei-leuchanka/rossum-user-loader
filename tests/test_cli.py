import pytest

from rossum_user_loader import cli, core


@pytest.fixture(autouse=True)
def _no_network_verify(monkeypatch):
    # Token verification makes a real API call; stub it out by default so the
    # connection tests stay offline. Tests that care override it.
    monkeypatch.setattr(cli.core, "verify_credentials", lambda domain, token: None)


@pytest.fixture(autouse=True)
def _clear_rossum_env(monkeypatch):
    # Keep tests hermetic: a developer's local .env must not leak into prompts.
    for var in ("ROSSUM_DOMAIN", "ROSSUM_ORG_ID", "ROSSUM_USERNAME", "ROSSUM_PASSWORD"):
        monkeypatch.delenv(var, raising=False)


def test_console_reporter_applies_level_colors(capsys):
    for level, color in [("ok", cli.GREEN), ("error", cli.RED), ("skip", cli.RED), ("info", cli.BLUE)]:
        cli._console_reporter(level, "msg")
        out = capsys.readouterr().out
        assert out.startswith(color)
        assert "msg" in out
        assert out.rstrip("\n").endswith(cli.RESET)


def test_export_log_writes_csv_next_to_input(tmp_path):
    logger = core.Logger()
    logger.add("User created - {}", email="a@x.io")
    input_file = tmp_path / "users.xlsx"
    cli._export_log(logger, str(input_file))
    written = list(tmp_path.glob("user_load_*.csv"))
    assert len(written) == 1


def test_gather_connection_default_token_selection(monkeypatch):
    # Default auth method is token: press Enter at the selection, enter token (hidden).
    from rossum_api.dtos import Token
    inputs = iter(["https://x.rossum.app/api/v1", "", "42"])  # domain, auth-choice (blank=token), org
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "TYPED-TOKEN")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    conn = cli.gather_connection()
    assert isinstance(conn["credentials"], Token)
    assert conn["credentials"].token == "TYPED-TOKEN"
    assert conn["organization"] == "https://x.rossum.app/api/v1/organizations/42"


def test_gather_connection_username_password_generates_token(monkeypatch):
    # Choosing 'U' exchanges username+password for a token via /auth/login.
    from rossum_api.dtos import Token
    inputs = iter(["https://x.rossum.app/api/v1", "u", "jane@corp.com", "42"])  # domain, choice, username, org
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "s3cret")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    captured = {}

    def fake_gen(domain, username, password):
        captured.update(domain=domain, username=username, password=password)
        return "GEN-TOKEN"

    monkeypatch.setattr(cli.core, "generate_token", fake_gen)
    conn = cli.gather_connection()
    assert isinstance(conn["credentials"], Token)
    assert conn["credentials"].token == "GEN-TOKEN"
    assert captured == {
        "domain": "https://x.rossum.app/api/v1",
        "username": "jane@corp.com",
        "password": "s3cret",
    }


def test_gather_connection_env_token_skips_selection(monkeypatch):
    from rossum_api.dtos import Token
    inputs = iter(["https://x.rossum.app/api/v1", "42"])  # domain, org (no selection / no getpass)
    monkeypatch.setenv("ROSSUM_API_TOKEN", "ENVTOKEN")

    def _boom(*a, **k):
        raise AssertionError("getpass must not be called when an env token is set")

    monkeypatch.setattr(cli.getpass, "getpass", _boom)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    conn = cli.gather_connection()
    assert isinstance(conn["credentials"], Token)
    assert conn["credentials"].token == "ENVTOKEN"


def test_gather_connection_fully_from_env_never_prompts(monkeypatch):
    # With domain, org and token in the environment nothing is prompted at all.
    monkeypatch.setenv("ROSSUM_DOMAIN", "https://x.rossum.app/api/v1")
    monkeypatch.setenv("ROSSUM_ORG_ID", "42")
    monkeypatch.setenv("ROSSUM_API_TOKEN", "ENVTOKEN")

    def _boom(*a, **k):
        raise AssertionError("no prompt may be shown when the env provides everything")

    monkeypatch.setattr("builtins.input", _boom)
    monkeypatch.setattr(cli.getpass, "getpass", _boom)
    conn = cli.gather_connection()
    assert conn["domain"] == "https://x.rossum.app/api/v1"
    assert conn["credentials"].token == "ENVTOKEN"
    assert conn["organization"] == "https://x.rossum.app/api/v1/organizations/42"


def test_gather_connection_env_username_password_generates_token(monkeypatch):
    # ROSSUM_USERNAME+ROSSUM_PASSWORD skip the auth menu and /auth/login directly.
    monkeypatch.setenv("ROSSUM_DOMAIN", "https://x.rossum.app/api/v1")
    monkeypatch.setenv("ROSSUM_ORG_ID", "42")
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setenv("ROSSUM_USERNAME", "jane@corp.com")
    monkeypatch.setenv("ROSSUM_PASSWORD", "s3cret")

    def _boom(*a, **k):
        raise AssertionError("no prompt may be shown when the env provides everything")

    monkeypatch.setattr("builtins.input", _boom)
    monkeypatch.setattr(cli.getpass, "getpass", _boom)
    captured = {}

    def fake_gen(domain, username, password):
        captured.update(domain=domain, username=username, password=password)
        return "GEN-TOKEN"

    monkeypatch.setattr(cli.core, "generate_token", fake_gen)
    conn = cli.gather_connection()
    assert conn["credentials"].token == "GEN-TOKEN"
    assert captured == {
        "domain": "https://x.rossum.app/api/v1",
        "username": "jane@corp.com",
        "password": "s3cret",
    }


def test_env_token_beats_env_username_password(monkeypatch):
    # Precedence: an env token wins; /auth/login must not be hit.
    monkeypatch.setenv("ROSSUM_DOMAIN", "https://x.rossum.app/api/v1")
    monkeypatch.setenv("ROSSUM_ORG_ID", "42")
    monkeypatch.setenv("ROSSUM_API_TOKEN", "ENVTOKEN")
    monkeypatch.setenv("ROSSUM_USERNAME", "jane@corp.com")
    monkeypatch.setenv("ROSSUM_PASSWORD", "s3cret")

    def _no_login(*a, **k):
        raise AssertionError("generate_token must not be called when a token is set")

    monkeypatch.setattr(cli.core, "generate_token", _no_login)
    conn = cli.gather_connection()
    assert conn["credentials"].token == "ENVTOKEN"


def test_env_username_password_rejected_exits_cleanly(monkeypatch, capsys):
    # A bad stored password fails fast with a clear message, no retry loop.
    monkeypatch.setenv("ROSSUM_DOMAIN", "https://x.rossum.app/api/v1")
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setenv("ROSSUM_USERNAME", "jane@corp.com")
    monkeypatch.setenv("ROSSUM_PASSWORD", "wrong")

    def fake_gen(domain, username, password):
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr(cli.core, "generate_token", fake_gen)
    with pytest.raises(SystemExit) as ei:
        cli.gather_connection()
    assert ei.value.code == 1
    assert "ROSSUM_USERNAME" in capsys.readouterr().out


def test_env_username_without_password_still_prompts(monkeypatch):
    # Only one half set -> fall back to the normal interactive flow.
    monkeypatch.setenv("ROSSUM_USERNAME", "jane@corp.com")
    inputs = iter(["https://x.rossum.app/api/v1", "", "42"])  # domain, auth-choice, org
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "TYPED-TOKEN")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    conn = cli.gather_connection()
    assert conn["credentials"].token == "TYPED-TOKEN"


def test_run_web_subcommand_invokes_launcher(monkeypatch):
    called = {}
    from rossum_user_loader.web import launcher
    monkeypatch.setattr(launcher, "launch", lambda: called.setdefault("launched", True))
    cli.run(["web"])
    assert called.get("launched")


def test_gather_connection_reprompts_on_bad_org_id(monkeypatch):
    inputs = iter(["https://x.rossum.app/api/v1", "", "abc", "42"])  # domain, token-choice, bad org, good org
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "TKN")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    conn = cli.gather_connection()
    assert conn["organization"] == "https://x.rossum.app/api/v1/organizations/42"


def test_gather_connection_reprompts_on_bad_url(monkeypatch):
    inputs = iter(["ftp://nope", "https://x.rossum.app/api/v1", "", "42"])  # bad url, good url, token-choice, org
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "TKN")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    conn = cli.gather_connection()
    assert conn["domain"] == "https://x.rossum.app/api/v1"


def test_read_input_rows_uses_csv_reader_for_csv(tmp_path):
    p = tmp_path / "load.csv"
    p.write_text(
        "auth_type;email;first_name;last_name;username;oidc_id;role;queue_ids;can_approve\n"
        "password;a@x.io;A;B;;;annotator;1;no\n",
        encoding="utf-8",
    )
    rows = cli._read_input_rows({"file_path": str(p), "sheet_name": ""})
    assert rows and rows[0]["email"] == "a@x.io"


def test_gather_config_skips_sheet_prompt_for_csv(monkeypatch):
    answers = iter(["https://x.rossum.app/api/v1", "42", "/tmp/load.csv"])
    monkeypatch.setenv("ROSSUM_API_TOKEN", "ENVTOKEN")  # skip getpass
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    cfg = cli.gather_config()
    assert cfg["file_path"] == "/tmp/load.csv"
    assert cfg["sheet_name"] == ""


def test_gather_config_prompts_sheet_for_xlsx(monkeypatch):
    answers = iter(["https://x.rossum.app/api/v1", "42", "/tmp/load.xlsx", "Sheet1"])
    monkeypatch.setenv("ROSSUM_API_TOKEN", "ENVTOKEN")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    cfg = cli.gather_config()
    assert cfg["sheet_name"] == "Sheet1"


def test_load_users_writes_log_even_when_collect_data_fails(tmp_path, monkeypatch):
    import asyncio

    from rossum_user_loader import ratelimit

    p = tmp_path / "load.csv"
    p.write_text(
        "auth_type;email;first_name;last_name;username;oidc_id;role;queue_ids;can_approve\n"
        "password;ex@x.io;E;X;;;annotator;;no\n"
        "password;a@x.io;A;B;;;annotator;;no\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "AsyncRossumAPIClient", lambda **k: object())
    monkeypatch.setattr(cli, "Token", lambda **k: None)
    monkeypatch.setattr(ratelimit, "install", lambda c: c)

    async def boom(client):
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr(cli.core, "collect_data", boom)
    config = {
        "credentials": None, "domain": "https://x/api/v1",
        "organization": "https://x/api/v1/organizations/1",
        "file_path": str(p), "sheet_name": "",
    }
    asyncio.run(cli.load_users(config))  # must NOT raise

    logs = list(tmp_path.glob("user_load_*.csv"))
    assert len(logs) == 1
    assert "401 Unauthorized" in logs[0].read_text()


def test_load_users_processes_every_row_and_logs_summary(tmp_path, monkeypatch):
    import asyncio
    from tests.conftest import FakeClient, FakeGroup

    from rossum_user_loader import ratelimit

    p = tmp_path / "load.csv"
    p.write_text(
        "auth_type;email;first_name;last_name;username;oidc_id;role;queue_ids;can_approve\n"
        "password;u1@x.io;One;A;;;annotator;;no\n"
        "password;u2@x.io;Two;B;;;annotator;;no\n",
        encoding="utf-8",
    )
    fake = FakeClient()
    monkeypatch.setattr(cli, "AsyncRossumAPIClient", lambda **k: fake)
    monkeypatch.setattr(cli, "Token", lambda **k: None)
    monkeypatch.setattr(ratelimit, "install", lambda c: c)

    async def collect(client):
        return ([], [FakeGroup("annotator", "https://x/g/1")], [])

    monkeypatch.setattr(cli.core, "collect_data", collect)
    cfg = {
        "credentials": None, "domain": "https://x/api/v1",
        "organization": "https://x/api/v1/organizations/1",
        "file_path": str(p), "sheet_name": "",
    }
    asyncio.run(cli.load_users(cfg))

    # No row is dropped — BOTH users are created.
    assert [u["username"] for u in fake.created] == ["u1@x.io", "u2@x.io"]
    log = next(tmp_path.glob("user_load_*.csv")).read_text()
    assert "u1@x.io" in log and "u2@x.io" in log
    assert "Summary -" in log


def test_select_arrow_returns_none_when_not_a_tty():
    # No TTY under pytest → returns None so the caller uses the text fallback.
    assert cli._select_arrow("pick", [("A", "a"), ("B", "b")]) is None


def test_gather_connection_reprompts_on_rejected_token(monkeypatch):
    # A typed token that Rossum rejects re-prompts until a valid one is entered.
    from rossum_api.dtos import Token
    inputs = iter(["https://x.rossum.app/api/v1", "", "42"])  # domain, token-choice, org
    tokens = iter(["BAD-TOKEN", "GOOD-TOKEN"])
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: next(tokens))
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    calls = {"n": 0}

    def verify(domain, token):
        calls["n"] += 1
        if token == "BAD-TOKEN":
            raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr(cli.core, "verify_credentials", verify)  # override autouse stub
    conn = cli.gather_connection()
    assert isinstance(conn["credentials"], Token)
    assert conn["credentials"].token == "GOOD-TOKEN"
    assert calls["n"] == 2  # rejected once, accepted on retry


def test_gather_connection_gives_up_after_three_bad_tokens(monkeypatch):
    inputs = iter(["https://x.rossum.app/api/v1", ""])  # domain, token-choice (org never reached)
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "BAD")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    calls = {"n": 0}

    def verify(domain, token):
        calls["n"] += 1
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr(cli.core, "verify_credentials", verify)
    with pytest.raises(SystemExit) as ei:
        cli.gather_connection()
    assert ei.value.code == 1
    assert calls["n"] == cli.MAX_AUTH_ATTEMPTS  # exactly 3 attempts, then stop


def test_load_users_client_is_rate_limited(monkeypatch, tmp_path):
    import asyncio as aio

    from rossum_api.dtos import Token

    from rossum_user_loader import ratelimit

    installed = []
    monkeypatch.setattr(ratelimit, "install", lambda c: installed.append(c) or c)

    async def stop_here(client):
        raise RuntimeError("stop-after-client-construction")

    monkeypatch.setattr(cli.core, "collect_data", stop_here)
    p = tmp_path / "load.csv"
    p.write_text("auth_type;email;first_name;last_name;username;oidc_id;role;queue_ids;can_approve\n")
    config = {
        "credentials": Token(token="t"), "domain": "https://x/api/v1",
        "organization": "https://x/api/v1/organizations/1",
        "file_path": str(p), "sheet_name": "",
    }
    aio.run(cli.load_users(config))  # exception is caught internally
    assert len(installed) == 1


def test_gather_connection_gives_up_after_three_failed_logins(monkeypatch):
    inputs = iter(["https://x.rossum.app/api/v1", "u", "jane@corp.com", "jane@corp.com", "jane@corp.com"])
    monkeypatch.delenv("ROSSUM_API_TOKEN", raising=False)
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "pw")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(inputs))
    calls = {"n": 0}

    def gen(domain, username, password):
        calls["n"] += 1
        raise RuntimeError("login failed")

    monkeypatch.setattr(cli.core, "generate_token", gen)
    with pytest.raises(SystemExit) as ei:
        cli.gather_connection()
    assert ei.value.code == 1
    assert calls["n"] == cli.MAX_AUTH_ATTEMPTS
