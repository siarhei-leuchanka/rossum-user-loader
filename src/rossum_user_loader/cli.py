"""Command-line front end for the Rossum user loader.

Gathers configuration interactively, reads rows from a spreadsheet, and drives
the loading logic in ``core``. All prompts live inside functions so importing
this module (e.g. for the entry point or tests) has no side effects.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import getpass
import os
from typing import NoReturn

from rossum_api import AsyncRossumAPIClient
from rossum_api.dtos import Token

from rossum_user_loader import __version__, core, csvio, excel, validation

# ANSI colors used in console output.
RED = "\033[91m"
GREEN = "\033[92m"
BLUE = "\033[94m"
MAGENTA = "\033[35m"
RESET = "\033[0m"

# How many times the user may retry bad credentials/token before we give up.
MAX_AUTH_ATTEMPTS = 3


def _give_up() -> NoReturn:
    print(f"{RED}Giving up after {MAX_AUTH_ATTEMPTS} failed attempts.{RESET}")
    raise SystemExit(1)


def _prompt_valid(label: str, validator, env_value=None, secret=False):
    """Prompt until ``validator`` accepts the input. If ``env_value`` is set,
    validate it once (no loop) so a bad env var fails fast with a clear error.
    ``secret=True`` reads via getpass so the value is not echoed to the terminal."""
    if env_value:
        return validator(env_value)
    read = getpass.getpass if secret else input
    while True:
        try:
            return validator(read(label))
        except validation.ValidationError as exc:
            print(f"{RED}{exc}{RESET}")


def _select_arrow(title: str, options, default_index: int = 0):
    """Arrow-key menu on an interactive POSIX terminal. ``options`` is a list of
    (label, value); returns the chosen value. Returns None when a real TUI isn't
    possible (not a TTY, no termios, Windows) so the caller can fall back to text.
    """
    import sys

    stdin, stdout = sys.stdin, sys.stdout
    if not (stdin.isatty() and stdout.isatty()):
        return None
    try:
        import termios
        import tty
    except Exception:  # noqa: BLE001 - not POSIX / no terminal
        return None

    idx = default_index
    n = len(options)
    stdout.write(f"{title}\n  (↑/↓ to move, Enter to select)\n")

    def render():
        for i, (label, _value) in enumerate(options):
            if i == idx:
                stdout.write(f"\r\033[7m› {label}\033[0m\033[K\n")
            else:
                stdout.write(f"\r  {label}\033[K\n")
        stdout.flush()

    render()
    fd = stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            ch = stdin.read(1)
            if ch in ("\r", "\n"):
                break
            if ch == "\x03":  # Ctrl-C
                raise KeyboardInterrupt
            if ch == "\x1b":  # escape sequence — arrow keys
                seq = stdin.read(2)
                if seq.endswith("A"):
                    idx = (idx - 1) % n
                elif seq.endswith("B"):
                    idx = (idx + 1) % n
            elif ch == "k":
                idx = (idx - 1) % n
            elif ch == "j":
                idx = (idx + 1) % n
            stdout.write(f"\033[{n}A")  # move back up over the option lines
            render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return options[idx][1]


def _select_auth_method() -> str:
    """Ask whether to authenticate with a token or username+password (token is
    the default). Uses an arrow-key menu when possible, else a typed T/U prompt."""
    options = [("API token", "token"), ("Username + password", "userpass")]
    chosen = _select_arrow("How do you want to authenticate?", options, default_index=0)
    if chosen is not None:
        return chosen
    # Fallback for non-interactive / unsupported terminals.
    while True:
        choice = input("Authenticate with [T]oken or [U]sername+password? [T]: ").strip().lower()
        if choice in ("", "t", "token"):
            return "token"
        if choice in ("u", "user", "username", "userpass", "p", "password"):
            return "userpass"
        print(f"{RED}Please enter 'T' for token or 'U' for username+password.{RESET}")


def _resolve_token(domain: str) -> str:
    """Obtain an API token: from ROSSUM_API_TOKEN, entered directly, or generated
    from username+password via the Rossum /auth/login endpoint. Every API call
    then uses this token — the credentials are only ever exchanged for one."""
    env_token = os.environ.get("ROSSUM_API_TOKEN")
    if env_token:
        token = validation.validate_token(env_token)
        try:
            core.verify_credentials(domain, token)
        except Exception as exc:  # noqa: BLE001
            print(f"{RED}ROSSUM_API_TOKEN was rejected by Rossum.\n"
                  f"Details: {exc}{RESET}")
            raise SystemExit(1) from None
        return token

    if _select_auth_method() == "token":
        # Verify the token is real (one authenticated call); re-prompt if rejected,
        # up to MAX_AUTH_ATTEMPTS times, then give up.
        for attempt in range(1, MAX_AUTH_ATTEMPTS + 1):
            token = _prompt_valid(
                "Rossum API token (input hidden): ", validation.validate_token, secret=True
            )
            try:
                core.verify_credentials(domain, token)
                return token
            except Exception as exc:  # noqa: BLE001
                print(f"{RED}That token was rejected by Rossum — check the token "
                      f"(and the domain URL). [attempt {attempt}/{MAX_AUTH_ATTEMPTS}]"
                      f"\nDetails: {exc}{RESET}")
        _give_up()

    # Username + password → exchange for a token via /auth/login (retry, capped).
    for attempt in range(1, MAX_AUTH_ATTEMPTS + 1):
        username = _prompt_valid("Rossum username (email): ", validation.validate_username)
        password = _prompt_valid(
            "Rossum password (input hidden): ", validation.validate_password, secret=True
        )
        try:
            return core.generate_token(domain, username, password)
        except Exception as exc:  # noqa: BLE001
            print(
                f"{RED}Login failed — check your username, password, and the domain "
                f"URL. [attempt {attempt}/{MAX_AUTH_ATTEMPTS}]\nDetails: {exc}{RESET}"
            )
    _give_up()


def gather_connection() -> dict:
    """Collect and validate the domain, credentials (token), and organization."""
    domain = _prompt_valid(
        "Please enter Rossum domain url with /v1 in the end "
        "e.g. https://custom-domain.rossum.app/api/v1: ",
        validation.validate_domain,
    )
    token = _resolve_token(domain)
    organization_id = _prompt_valid(
        "What is the target Organization ID: ", validation.validate_org_id
    )
    return {
        "credentials": Token(token=token),
        "domain": domain,
        "organization": f"{domain}/organizations/{organization_id}",
    }


def gather_config() -> dict:
    """Connection details plus the input file (.csv or .xlsx) for the CLI loader.

    CSV has no worksheets, so the sheet-name prompt is only shown for .xlsx.
    """
    conn = gather_connection()
    file_path = input("Provide a path to load file (.csv or .xlsx): ").strip().strip("'\"")
    sheet_name = ""
    if not file_path.lower().endswith(".csv"):
        sheet_name = input("Provide a sheet name to load file: ").strip()
    return {**conn, "file_path": file_path, "sheet_name": sheet_name}


def _read_input_rows(config: dict) -> list[dict]:
    """Read input rows, choosing the reader by file extension (.csv vs .xlsx)."""
    if config["file_path"].lower().endswith(".csv"):
        return csvio.read_rows(config["file_path"], core.REQUIRED_COLUMNS)
    return excel.read_rows(
        config["file_path"], config["sheet_name"], core.REQUIRED_COLUMNS
    )


async def load_users(config: dict) -> None:
    client = AsyncRossumAPIClient(
        base_url=config["domain"], credentials=config["credentials"]
    )

    # A log is ALWAYS written — even if reading the file or reaching Rossum
    # fails — so every run leaves a record (the abort reason included).
    logger = core.Logger()
    try:
        # Every data row is processed as-is; the header is consumed by the
        # reader. No row is dropped or special-cased.
        rows = _read_input_rows(config)
        info = f"Read {len(rows)} data row(s) to process"
        print(f"{GREEN}{info}{RESET}")
        if not rows:
            print(f"{RED}No user rows to process — nothing to do.{RESET}")

        try:
            active_users, org_groups, org_queues = await core.collect_data(client)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(core.connection_error_message(exc)) from exc

        logger = await core.run_load(
            client,
            rows,
            config["organization"],
            org_groups,
            org_queues,
            active_users,
            on_result=_console_reporter,
        )
        logger.add("Info - " + info)
        s = core.summarize(logger.get())
        summary = (
            f"created {s['created']}, patched {s['patched']}, "
            f"skipped {s['skipped']}, errors {s['errors']} (of {s['total']})"
        )
        logger.add("Summary - " + summary)
        print(f"{GREEN}Done — {summary}{RESET}")
    except Exception as exc:  # noqa: BLE001
        logger.add(f"Error - load aborted - {exc}")
        print(f"{RED}Load aborted - {exc}{RESET}")
    finally:
        _export_log(logger, config["file_path"])


def _console_reporter(level: str, message: str) -> None:
    color = {"ok": GREEN, "error": RED, "skip": RED, "info": BLUE}.get(level, "")
    print(f"{color}{message}{RESET}")


def _export_log(logger: core.Logger, input_file_path: str) -> None:
    """Write the run log (CSV) next to the input file."""
    directory = os.path.dirname(input_file_path)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    name = f"user_load_{timestamp}"
    base = os.path.join(directory, name) if directory else name
    out_path = csvio.write_log(base, logger.get())
    print(f"{GREEN}Log written to{RESET} {os.path.abspath(out_path)}")


def run(argv: list[str] | None = None) -> None:
    """Console-script entry point.

    With no subcommand, runs the interactive spreadsheet loader. ``web`` starts
    the local web UI. ``--help``/``--version`` return without prompting.
    """
    parser = argparse.ArgumentParser(
        prog="rossum-user-loader",
        description="Bulk-load users into Rossum from a spreadsheet.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("web", help="Launch the local web UI to prepare and load the user batch")
    args = parser.parse_args(argv)

    if args.command == "web":
        from rossum_user_loader.web import launcher

        launcher.launch()
        return

    config = gather_config()
    asyncio.run(load_users(config))


if __name__ == "__main__":
    run()
