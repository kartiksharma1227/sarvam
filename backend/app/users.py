"""Manage accounts from the command line.

    python -m app.users list
    python -m app.users create EMAIL [--name NAME] [--admin]   asks for a password
    python -m app.users set-password EMAIL                     asks for a new password
    python -m app.users delete EMAIL                           removes the account (not its videos)

The password is read from a prompt (or the MINDSKETCH_PASSWORD environment variable, for scripts).
"""

import argparse
import asyncio
import getpass
import os

from app.auth import hash_password
from app.db import init_db
from app.models.job import Job
from app.models.user import User
from app.models.video import Video


def _password() -> str:
    password = os.environ.get("MINDSKETCH_PASSWORD") or getpass.getpass(
        "Password (min 8 characters): "
    )
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters")
    return password


async def main(args) -> None:
    client = await init_db()
    try:
        if args.command == "list":
            for u in await User.find_all().sort("+created_at").to_list():
                jobs = await Job.find(Job.owner_id == u.id).count()
                print(
                    f"{u.email:<32} {'admin' if u.is_admin else 'user':<6} {jobs} videos  {u.name}"
                )
            return
        email = args.email.strip().lower()
        user = await User.find_one(User.email == email)
        if args.command == "create":
            if user:
                raise SystemExit(f"{email} already exists")
            first = await User.count() == 0
            user = await User(
                email=email,
                name=args.name or "",
                password_hash=hash_password(_password()),
                is_admin=args.admin or first,
            ).insert()
            if user.is_admin and first:
                await Job.find({"owner_id": None}).update(
                    {"$set": {"owner_id": user.id}}
                )
                await Video.find({"owner_id": None}).update(
                    {"$set": {"owner_id": user.id}}
                )
            print(f"Created {email}{' (admin)' if user.is_admin else ''}")
        elif args.command == "delete":
            if not user:
                raise SystemExit(f"No account {email}")
            if user.is_admin:
                raise SystemExit("Refusing to delete the admin account")
            await user.delete()
            print(f"Deleted {email}")
        elif args.command == "set-password":
            if not user:
                raise SystemExit(f"No account {email}")
            user.password_hash = hash_password(_password())
            # Logs out every browser signed in with the old password.
            user.session_version += 1
            await user.set(
                {
                    "password_hash": user.password_hash,
                    "session_version": user.session_version,
                }
            )
            print(f"Password changed for {email} (signed out everywhere)")
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m app.users")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    create = sub.add_parser("create")
    create.add_argument("email")
    create.add_argument("--name")
    create.add_argument("--admin", action="store_true")
    reset = sub.add_parser("set-password")
    reset.add_argument("email")
    sub.add_parser("delete").add_argument("email")
    asyncio.run(main(parser.parse_args()))
