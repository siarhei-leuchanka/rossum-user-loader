import csv

from rossum_user_loader import csvio


def test_write_log_produces_csv_with_union_headers(tmp_path):
    records = [
        {"Messages": "ok", "email": "a@x.io", "groups": ["g1", "g2"]},
        {"Messages": "skip", "username": "u2"},
    ]
    out = csvio.write_log(str(tmp_path / "log"), records)

    assert out.endswith(".csv")
    with open(out, newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=csvio.DELIMITER))

    assert rows[0]["Messages"] == "ok"
    assert rows[0]["groups"] == "g1\ng2"      # lists joined by newline
    assert rows[1]["username"] == "u2"
    assert rows[0]["username"] == ""          # missing key -> blank


import pytest


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=csvio.DELIMITER)
        writer.writerow(header)
        writer.writerows(rows)


def test_read_rows_returns_stripped_dicts(tmp_path):
    p = tmp_path / "in.csv"
    _write_csv(p, ["email", "role"], [["  a@x.io ", "annotator"], ["b@x.io", ""]])
    rows = csvio.read_rows(str(p), ("email", "role"))
    assert rows[0] == {"email": "a@x.io", "role": "annotator"}
    assert rows[1]["role"] == ""


def test_read_rows_raises_on_missing_required_column(tmp_path):
    p = tmp_path / "in.csv"
    _write_csv(p, ["email"], [["a@x.io"]])
    with pytest.raises(RuntimeError, match="Missing required column"):
        csvio.read_rows(str(p), ("email", "role"))


import os


def test_template_path_points_to_existing_csv():
    path = csvio.template_path()
    assert path.endswith("user_load_template.csv")
    assert os.path.exists(path)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header = next(csv.reader(fh, delimiter=csvio.DELIMITER))
    assert "username" in header
