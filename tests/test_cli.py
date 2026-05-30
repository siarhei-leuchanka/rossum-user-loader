from rossum_user_loader import cli, core


def test_console_reporter_colors(capsys):
    cli._console_reporter("ok", "created")
    cli._console_reporter("error", "boom")
    out = capsys.readouterr().out
    assert "created" in out
    assert "boom" in out


def test_export_log_writes_csv_next_to_input(tmp_path):
    logger = core.Logger()
    logger.add("User created - {}", email="a@x.io")
    input_file = tmp_path / "users.xlsx"
    cli._export_log(logger, str(input_file))
    written = list(tmp_path.glob("user_load_*.csv"))
    assert len(written) == 1
