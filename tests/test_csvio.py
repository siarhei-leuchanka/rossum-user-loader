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
        rows = list(csv.DictReader(fh))

    assert rows[0]["Messages"] == "ok"
    assert rows[0]["groups"] == "g1\ng2"      # lists joined by newline
    assert rows[1]["username"] == "u2"
    assert rows[0]["username"] == ""          # missing key -> blank
