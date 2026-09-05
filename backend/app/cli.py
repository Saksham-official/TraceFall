"""Administrative commands.

There are no seeded credentials in any build: create-admin is interactive and mandatory.
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.paths import resolve
from app.core.security import MIN_PASSWORD_LENGTH, hash_password
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.db.session import SessionFactory
from app.labels import loader


def default_labels_dir() -> Path:
    return resolve(get_settings().label_data_path, setting="LABEL_DATA_PATH")


# Passwords that clear the length rule but are still guessable. Entries shorter than
# MIN_PASSWORD_LENGTH would be unreachable, so every entry here is long enough to matter.
COMMON_PASSWORDS = {
    "password1234",
    "passw0rd1234",
    "administrator",
    "changeme1234",
    "tracefall123",
    "qwertyuiop12",
    "letmein12345",
    "123456789012",
}


async def create_admin(email: str | None, full_name: str | None) -> int:
    email = (email or input("Email: ")).strip().lower()
    full_name = (full_name or input("Full name: ")).strip()
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match", file=sys.stderr)
        return 1
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters", file=sys.stderr)
        return 1
    if password.lower() in COMMON_PASSWORDS:
        print("That password is too common", file=sys.stderr)
        return 1

    async with SessionFactory() as session:
        if await session.scalar(select(User.id).where(User.email == email)):
            print(f"A user with email {email} already exists", file=sys.stderr)
            return 1
        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=UserRole.ADMIN,
            )
        )
        await session.commit()
    print(f"Created admin {email}")
    return 0


async def load_labels(directory: Path) -> int:
    """Ingest the curated label datasets. Re-running it changes nothing."""
    if not directory.is_dir():
        print(f"No label directory at {directory}", file=sys.stderr)
        return 1

    failed = False
    async with SessionFactory() as session:
        for summary in await loader.ingest_directory(session, directory):
            print(
                f"{summary.source}: {summary.labels_written} new labels, "
                f"{summary.entities_written} entities, {summary.addresses_written} addresses"
            )
            for address, reason in summary.rejected:
                # Rejections are printed, never swallowed: a dataset that silently loses
                # 6% of its rows is worse than one that fails loudly.
                print(f"  rejected {address}: {reason}", file=sys.stderr)
                failed = True
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="tracefall")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="Create an administrator account")
    admin.add_argument("--email")
    admin.add_argument("--full-name")
    labels = sub.add_parser("load-labels", help="Ingest the curated label datasets")
    labels.add_argument("--directory", type=Path, default=None)

    args = parser.parse_args()
    if args.command == "create-admin":
        return asyncio.run(create_admin(args.email, args.full_name))
    if args.command == "load-labels":
        return asyncio.run(load_labels(args.directory or default_labels_dir()))
    return 1


if __name__ == "__main__":
    sys.exit(main())
