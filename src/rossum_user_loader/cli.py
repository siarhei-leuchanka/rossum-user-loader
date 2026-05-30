"""Command-line front end for the Rossum user loader.

Gathers configuration interactively, reads rows from a spreadsheet, and drives
the loading logic in ``core``. All prompts live inside functions so importing
this module (e.g. for the entry point or tests) has no side effects.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os

from rossum_api import AsyncRossumAPIClient
from rossum_api.dtos import Token

from rossum_user_loader import __version__, core, csvio, excel

# ANSI colors used in console output.
RED = "\033[91m"
GREEN = "\033[92m"
BLUE = "\033[94m"
MAGENTA = "\033[35m"
RESET = "\033[0m"


def gather_config() -> dict:
    """Collect run configuration from prompts (token may come from env)."""
    token = os.environ.get("ROSSUM_API_TOKEN") or input(
        "Please enter your Rossum API token: "
    )
    domain = input(
        "Please enter Rossum domain url with /v1 in the end "
        "e.g. https://custom-domain.rossum.app/api/v1: "
    ).strip()
    organization_id = input("What is the target Organization ID: ").strip()
    file_path = input("Provide a path to load file: ").strip("'").strip()
    sheet_name = input("Provide a sheet name to load file: ").strip()

    return {
        "token": token,
        "domain": domain,
        "organization": f"{domain}/organizations/{organization_id}".strip(),
        "file_path": file_path,
        "sheet_name": sheet_name,
    }


async def load_users(config: dict) -> None:
    client = AsyncRossumAPIClient(
        base_url=config["domain"], credentials=Token(token=config["token"])
    )

    rows = excel.read_rows(
        config["file_path"], config["sheet_name"], core.REQUIRED_COLUMNS
    )
    print(f"{GREEN}All supported columns detected. Moving on{RESET}")

    try:
        active_users, org_groups, org_queues = await core.collect_data(client)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Can't get data from Rossum: {exc}") from exc

    # rows[1:] drops the template example row.
    logger = await core.run_load(
        client,
        rows[1:],
        config["organization"],
        org_groups,
        org_queues,
        active_users,
        on_result=_console_reporter,
    )

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
    print(f"{GREEN}Log written to{RESET} {out_path}")


def run(argv: list[str] | None = None) -> None:
    """Console-script entry point.

    Configuration is collected interactively; ``--help``/``--version`` return
    immediately without prompting so the command is well-behaved in scripts and
    package smoke tests.
    """
    parser = argparse.ArgumentParser(
        prog="rossum-user-loader",
        description="Bulk-load users into Rossum from a spreadsheet.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args(argv)

    config = gather_config()
    asyncio.run(load_users(config))


if __name__ == "__main__":
    run()
