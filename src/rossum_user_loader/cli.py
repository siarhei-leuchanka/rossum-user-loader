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

from rossum_user_loader import __version__, core, excel

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
    logger = core.Logger()

    rows = excel.read_rows(
        config["file_path"], config["sheet_name"], core.SUPPORTED_COLUMNS.keys()
    )
    print(f"{GREEN}All supported columns detected. Moving on{RESET}")

    try:
        active_users, org_groups, org_queues = await core.collect_data(client)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Can't get data from Rossum: {exc}") from exc

    existing_emails = {u["email"].lower().strip() for u in active_users}

    # The first data row in the template is an example/instructions row.
    for row in rows[1:]:
        try:
            user_data = core.prepare_user_data(
                row, config["organization"], org_groups, org_queues
            )
        except ValueError as exc:
            print(f"{RED}Skipping row{RESET} - {exc}")
            logger.add(f"Error - invalid user data - {exc}", email=row.get("email", ""))
            continue

        if user_data["auth_type"] not in ("sso", "password") or not user_data["email"]:
            print(f"Check user data entry - {user_data['email']}")
            logger.add("Error-check user data entry. No required fields.", **user_data)
            continue

        if user_data["email"].lower() in existing_emails:
            print(f"{RED}User Exists{RESET} - {user_data['email']}")
            logger.add("Skipped-User Exists", **user_data)
            continue

        print(f"{BLUE}Creating User: {RESET}", user_data["email"])
        try:
            response = await core.create_user(client, user_data)
            logger.add(f"User created - {response}", **user_data)
            print(f"User created - {response}")
        except Exception as exc:  # noqa: BLE001
            print(f"{RED}ERROR - user most likely not created{RESET} {exc}")
            logger.add(f"Error - user not created - {exc}", **user_data)
            continue

        if user_data["auth_type"] == "password":
            try:
                response = await core.reset_password(client, user_data["email"])
                logger.add(f"Password reset - {response}", **user_data)
                print(
                    f"{MAGENTA}Password reset is done for user{RESET} "
                    f"{BLUE}{user_data['email']}{RESET} - {response}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"{RED}Password reset failed{RESET} {exc}")
                logger.add(f"Error - password reset failed - {exc}", **user_data)

    _export_log(logger, config["file_path"])


def _export_log(logger: core.Logger, input_file_path: str) -> None:
    """Write the run log next to the input file."""
    directory = os.path.dirname(input_file_path)
    timestamp = datetime.datetime.now()
    base = os.path.join(directory, f"user_load_{timestamp}") if directory else f"user_load_{timestamp}"
    out_path = excel.write_log(base, logger.get())
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
