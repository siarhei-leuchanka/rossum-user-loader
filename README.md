# rossum-user-loader

Bulk-create and update users in [Rossum](https://rossum.ai), either from a
local web UI or from a CSV/xlsx file on the command line.

## Install

Install with [pipx](https://pipx.pypa.io) (isolated, no manual venv). Requires
Python 3.12 or newer.

```bash
pipx install git+https://github.com/siarhei-leuchanka/rossum-user-loader.git
```

## Update

```bash
pipx upgrade rossum-user-loader
```

Check with `rossum-user-loader --version`. If it still shows the old version,
run `pipx reinstall rossum-user-loader`, which always rebuilds from the latest
code. Release notes are in [CHANGELOG.md](CHANGELOG.md).

## Connecting to Rossum

Both modes start by asking for:

1. the API domain URL, e.g. `https://your-org.rossum.app/api/v1`;
2. how to sign in: **token** (the default) or **username + password**. With
   username/password the tool calls Rossum's `/auth/login` to get a token;
   either way every API call uses a token. Passwords and typed tokens are
   hidden as you type;
3. the target organization ID.

Any of these can be set in advance with environment variables, so you aren't
prompted: `ROSSUM_DOMAIN`, `ROSSUM_ORG_ID`, and either `ROSSUM_API_TOKEN` or
`ROSSUM_USERNAME` + `ROSSUM_PASSWORD` (the token wins when both are set).
Anything left unset is prompted for as usual. For example:

```bash
export ROSSUM_DOMAIN=https://your-org.rossum.app/api/v1
export ROSSUM_ORG_ID=123456
export ROSSUM_API_TOKEN=...      # or ROSSUM_USERNAME + ROSSUM_PASSWORD
rossum-user-loader web
```

All API traffic is limited to 8 requests per second (under Rossum's documented
limit of 10) and retries automatically when Rossum asks it to slow down, so
large loads stay within platform limits; they just take a little longer.

## Web UI

```bash
rossum-user-loader web
```

This opens a page in your browser, served only on your own machine
(`127.0.0.1`). The `?key=...` in its URL is a one-time key for that run, not
your Rossum token, which never leaves the tool.

- **Load Users**: add rows by hand, or download the CSV template with
  **⬇ Download CSV template** and load your filled-in file with
  **Load from CSV file**. Each row's *action* is **create** (new user) or
  **patch** (update an existing user, matched by username). Check the rows,
  then press **▶ Start Load**. Afterwards you can download a log of the run.
- **Existing Users**: the organization's current users (deleted users are not
  listed), including whether each is active and has verified their email.
  **Active users only** hides inactive users. You can copy users into the load
  list as patch rows, or **⬇ Download CSV** them in the same format the loader
  reads.

## Command line

```bash
rossum-user-loader
```

After connecting, give the path to a `.csv` or `.xlsx` file (the sheet name is
asked only for `.xlsx`). You can drag the file into the terminal window.
Every row in the file is loaded, so don't leave example rows in it. A
timestamped log (`user_load_<date-time>.csv`) is written next to your input
file, or to the current folder if the input file's folder doesn't exist.

## Templates

Both templates contain only the header row:

- **CSV** (recommended): **⬇ Download CSV template** in the web UI, or
  [download it from GitHub](https://raw.githubusercontent.com/siarhei-leuchanka/rossum-user-loader/main/src/rossum_user_loader/data/user_load_template.csv).
  Columns are separated by `;`.
- **xlsx** (CLI only):
  [download it from GitHub](https://github.com/siarhei-leuchanka/rossum-user-loader/raw/main/templates/user_load_template.xlsx).
  Users go on the `users` sheet.

## Columns

| column | required | meaning |
| --- | --- | --- |
| `auth_type` | yes | `password` or `sso`. Password users are sent a password-reset email when created |
| `email` | yes | the user's email |
| `first_name`, `last_name` | yes | name |
| `username` | no | login name, and what identifies an existing user. Blank means the email is used |
| `oidc_id` | yes (may be blank) | SSO identifier. Blank means the email is used |
| `role` | yes | must match an organization group name, e.g. `annotator` |
| `queue_ids` | yes (may be blank) | queue IDs, one per line within the cell. Ignored for the `admin` role |
| `can_approve` | yes | `yes` also adds the user to the `approver` group |
| `action` | no | `create` (the default) or `patch` to update an existing user |

A row whose username already exists is skipped when its action is `create`;
set it to `patch` to update that user instead. A patch updates the name,
`oidc_id`, `auth_type`, role and queues, but never the username or email.

## Project layout

```
src/rossum_user_loader/
  cli.py       # interactive front end + entry point
  core.py      # user-loading logic (no I/O), shared by the CLI and web UI
  csvio.py     # CSV read/write (templates, uploads, logs)
  excel.py     # xlsx reading (openpyxl)
  ratelimit.py # 8 req/s throttle + automatic retries when Rossum asks to slow down
  validation.py# input checks for prompts and the web UI
  data/        # CSV template shipped with the package
  web/         # Flask web UI (app, launcher, templates)
templates/     # xlsx template
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest
python -m rossum_user_loader   # or: rossum-user-loader
```
