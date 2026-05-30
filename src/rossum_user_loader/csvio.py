"""CSV input/output for the user loader (stdlib csv; no pandas).

CSV is the going-forward format for the web template, uploads, and logs. The
legacy xlsx reader stays in ``excel.py`` for the current CLI path.
"""

from __future__ import annotations

import csv


def _stringify(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return "" if value is None else str(value)


def write_log(path: str, records: list[dict]) -> str:
    """Write log records to ``<path>.csv`` and return the final path."""
    out_path = f"{path}.csv"

    columns: list[str] = []
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for record in records:
            writer.writerow([_stringify(record.get(col, "")) for col in columns])

    return out_path


def read_rows(file_path: str, required_columns) -> list[dict]:
    """Read a CSV into a list of ``{column: str}`` dicts (values stripped)."""
    with open(file_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames or []
        missing = [c for c in required_columns if c not in columns]
        if missing:
            raise RuntimeError(
                f"Missing required column(s): {missing}. Expected: {sorted(required_columns)}"
            )
        rows = []
        for raw in reader:
            rows.append(
                {k: ("" if v is None else str(v).strip()) for k, v in raw.items()}
            )
    return rows


def template_path() -> str:
    """Absolute path to the packaged CSV user-load template."""
    from importlib import resources

    return str(resources.files("rossum_user_loader").joinpath("data/user_load_template.csv"))
