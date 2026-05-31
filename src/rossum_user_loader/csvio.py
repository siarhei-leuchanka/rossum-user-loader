"""CSV input/output for the user loader (stdlib csv; no pandas).

CSV is the going-forward format for the web template, uploads, and logs. The
legacy xlsx reader stays in ``excel.py`` for the current CLI path.
"""

from __future__ import annotations

import csv

# Column delimiter for templates, uploads, and logs. ';' matches how Excel
# writes/opens CSV in many locales (where ',' is the decimal separator).
DELIMITER = ";"


def _stringify(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return "" if value is None else str(value)


# Leading chars a spreadsheet may interpret as a formula. Prefixing with a
# single quote neutralizes CSV/formula injection when a log is opened in Excel.
_CSV_INJECTION_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(text: str) -> str:
    return "'" + text if text and text[0] in _CSV_INJECTION_PREFIX else text


def write_log(path: str, records: list[dict]) -> str:
    """Write log records to ``<path>.csv`` and return the final path."""
    out_path = f"{path}.csv"

    columns: list[str] = []
    for record in records:
        for key in record:
            if key not in columns:
                columns.append(key)

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=DELIMITER)
        writer.writerow(columns)
        for record in records:
            writer.writerow([_csv_safe(_stringify(record.get(col, ""))) for col in columns])

    return out_path


def read_rows(file_path: str, required_columns) -> list[dict]:
    """Read a CSV into a list of ``{column: str}`` dicts (values stripped)."""
    with open(file_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=DELIMITER)
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
