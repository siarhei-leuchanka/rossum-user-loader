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
