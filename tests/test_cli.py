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
    answers = iter(["TOKEN", "https://x.rossum.app/api/v1", "42"])
    monkeypatch.setenv("ROSSUM_API_TOKEN", "")  # force prompt path
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    conn = cli.gather_connection()
    assert conn["token"] == "TOKEN"
    assert conn["organization"] == "https://x.rossum.app/api/v1/organizations/42"


def test_run_web_subcommand_invokes_launcher(monkeypatch):
    called = {}
    from rossum_user_loader.web import launcher
    monkeypatch.setattr(launcher, "launch", lambda: called.setdefault("launched", True))
    cli.run(["web"])
    assert called.get("launched")
