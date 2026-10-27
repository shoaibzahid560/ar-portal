"""
Maintenance commands, run from apps/api against the database in DATABASE_URL:

    .venv\\Scripts\\python -m app.cli create-admin you@company.com "Your Name"

There is deliberately no web endpoint for creating the first System Administrator.
"""

import argparse
import asyncio
import sys

from app.core import audit
from app.core.db import get_sessionmaker
from app.modules.auth import repository
from app.modules.users.models import User

ADMIN_ROLE = "system_admin"


async def create_admin(email: str, full_name: str) -> str:
    sessionmaker = get_sessionmaker()
    if sessionmaker is None:
        raise SystemExit("DATABASE_URL is not set. Add it to apps/api/.env first.")
    email = email.strip().lower()

    async with sessionmaker() as db, db.begin():
        role = await repository.get_role_by_key(db, ADMIN_ROLE)
        if role is None:
            raise SystemExit("Roles are missing. Run `alembic upgrade head` first.")

        user = await repository.get_user_by_email(db, email)
        if user is None:
            user = User(email=email, full_name=full_name.strip(), role_id=role.id, status="active")
            db.add(user)
            await db.flush()
            audit.record(
                db,
                action="user.created",
                entity_type="user",
                entity_id=user.id,
                after={"email": email, "role": ADMIN_ROLE, "status": "active"},
                request_id="cli:create-admin",
            )
            return f"Created System Administrator {email}."

        if user.role_id == role.id and user.status == "active":
            return f"{email} is already an active System Administrator. Nothing changed."

        before = {"role_id": user.role_id, "status": user.status}
        user.role_id, user.status = role.id, "active"
        audit.record(
            db,
            action="user.updated",
            entity_type="user",
            entity_id=user.id,
            before=before,
            after={"role": ADMIN_ROLE, "status": "active"},
            request_id="cli:create-admin",
        )
        return f"{email} is now an active System Administrator."


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="Create or restore the System Administrator account")
    admin.add_argument("email")
    admin.add_argument("full_name")
    args = parser.parse_args(argv)

    if args.command == "create-admin":
        print(asyncio.run(create_admin(args.email, args.full_name)))


if __name__ == "__main__":
    main(sys.argv[1:])
