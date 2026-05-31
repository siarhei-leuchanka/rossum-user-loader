from rossum_user_loader import cli, core


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


def test_gather_connection_builds_organization(monkeypatch):
    # Token is read via getpass (hidden), not input.
    answers = iter(["https://x.rossum.app/api/v1", "42"])
    monkeypatch.setenv("ROSSUM_API_TOKEN", "")  # force prompt path
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "TOKEN")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    conn = cli.gather_connection()
    assert conn["token"] == "TOKEN"
    assert conn["organization"] == "https://x.rossum.app/api/v1/organizations/42"


def test_gather_connection_token_from_env_skips_getpass(monkeypatch):
    answers = iter(["https://x.rossum.app/api/v1", "42"])
    monkeypatch.setenv("ROSSUM_API_TOKEN", "ENVTOKEN")

    def _boom(*a, **k):
        raise AssertionError("getpass must not be called when an env token is set")

    monkeypatch.setattr(cli.getpass, "getpass", _boom)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    conn = cli.gather_connection()
    assert conn["token"] == "ENVTOKEN"


def test_run_web_subcommand_invokes_launcher(monkeypatch):
    called = {}
    from rossum_user_loader.web import launcher
    monkeypatch.setattr(launcher, "launch", lambda: called.setdefault("launched", True))
    cli.run(["web"])
    assert called.get("launched")


def test_gather_connection_reprompts_on_bad_org_id(monkeypatch):
    answers = iter(["https://x.rossum.app/api/v1", "abc", "42"])
    monkeypatch.setenv("ROSSUM_API_TOKEN", "")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "TOKEN")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    conn = cli.gather_connection()
    assert conn["organization"] == "https://x.rossum.app/api/v1/organizations/42"


def test_gather_connection_reprompts_on_bad_url(monkeypatch):
    answers = iter(["ftp://nope", "https://x.rossum.app/api/v1", "42"])
    monkeypatch.setenv("ROSSUM_API_TOKEN", "")
    monkeypatch.setattr(cli.getpass, "getpass", lambda *a, **k: "TOKEN")
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
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
