# rossum-user-loader

Bulk-load users into [Rossum](https://rossum.ai) from a spreadsheet, via CLI.
A Flask web UI (replacing the spreadsheet) is planned — see `docs/`.

## Install

Pick one:

```bash
# Homebrew (once the tap repo is published)
brew install siarhei-leuchanka/tap/rossum-user-loader

# or straight from the source repo with pipx (isolated, no manual venv)
pipx install git+https://github.com/siarhei-leuchanka/rossum-user-loader.git
```

## Usage

```bash
rossum-user-loader
```

You'll be prompted for your API token (or set `ROSSUM_API_TOKEN`), the domain
URL, the target organization ID, the path to an `.xlsx` file, and the sheet
name. A timestamped log is written next to your input file.

Start from `templates/user_load_template.xlsx`. The first data row is treated
as an example and skipped; add real users beneath it. Columns:

| column | meaning |
| --- | --- |
| `auth_type` | `password` or `sso` |
| `email` | user email (also used as username) |
| `first_name`, `last_name` | name |
| `oidc_id` | SSO identifier; blank defaults to email |
| `role` | must match an organization group name (e.g. `annotator`) |
| `queue_ids` | newline-separated queue IDs (ignored for `admin` role) |
| `can_approve` | `yes` to also add the `approver` group |

## Project layout

```
src/rossum_user_loader/
  cli.py     # interactive front end + entry point
  core.py    # user-loading logic (no I/O) — reused by the future web UI
  excel.py   # spreadsheet read/write (openpyxl)
  web/       # placeholder for the planned Flask app
packaging/homebrew/   # Homebrew formula (lives in the tap repo)
templates/            # sample upload spreadsheet
```

## Development

```bash
pip install -e .
python -m rossum_user_loader   # or: rossum-user-loader
```

## Roadmap

See `TASKS.md` and `docs/superpowers/specs/`.
