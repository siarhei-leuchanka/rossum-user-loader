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
