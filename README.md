# rossum-user-loader

Bulk-load users into [Rossum](https://rossum.ai) from a spreadsheet, via CLI.
A Flask web UI (replacing the spreadsheet) is planned — see `docs/`.

## Install

Install with [pipx](https://pipx.pypa.io) (isolated, no manual venv):

```bash
pipx install git+https://github.com/siarhei-leuchanka/rossum-user-loader.git
```

## Usage

```bash
rossum-user-loader
```

After the domain URL, you choose how to authenticate — **token** (the default)
or **username + password**. With username/password the tool calls Rossum's
`/auth/login` to obtain a token; either way every API call uses a token. The
password (and a typed token) are entered hidden. Setting `ROSSUM_API_TOKEN`
skips the prompt entirely (handy for automation). Then you provide the target
organization ID and the path to a `.csv` or `.xlsx` file (sheet name is asked
only for `.xlsx`). A timestamped log is written next to your input file.

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
  web/       # Flask web UI (app, launcher, templates)
templates/   # sample upload spreadsheet
```

## Development

```bash
pip install -e .
python -m rossum_user_loader   # or: rossum-user-loader
```

## Roadmap

See `TASKS.md` and `docs/superpowers/specs/`.
