"""Create a SolTech staff account, or reset its password. There is no sign-up page (FR-10).

    docker compose run --rm api python -m app.staff_account staff@example.test

Prompts for the password twice. Resetting a password reactivates the account and signs it out everywhere.
"""

import argparse
import getpass
import sys

from app.auth.staff import set_staff_password
from app.db import engine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.staff_account", description=__doc__.splitlines()[0])
    parser.add_argument("email")
    email = parser.parse_args(argv).email.strip()

    password = getpass.getpass("New password: ")
    if getpass.getpass("Repeat password: ") != password:
        print("Passwords do not match; nothing changed.", file=sys.stderr)
        return 1
    try:
        with engine.begin() as conn:
            set_staff_password(conn, email, password)
    except ValueError as exc:
        print(f"{exc}; nothing changed.", file=sys.stderr)
        return 1
    print(f"Saved {email}. Any existing sessions for this account were signed out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
