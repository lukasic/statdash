import asyncio
import argparse
import sys

from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.db import SQLAlchemyUserDatabase

from app.core.auth import UserManager
from app.core.database import async_session_maker, create_db_and_tables
from app.models.user import User
from app.schemas.user import UserCreate


async def create_user(email: str, password: str, is_superuser: bool) -> None:
    await create_db_and_tables()

    async with async_session_maker() as session:
        user_db = SQLAlchemyUserDatabase(session, User)
        user_manager = UserManager(user_db)

        try:
            user = await user_manager.create(
                UserCreate(email=email, password=password, is_superuser=is_superuser)
            )
            role = "superuser" if user.is_superuser else "user"
            print(f"Created {role}: {user.email} (id={user.id})")
        except UserAlreadyExists:
            print(f"Error: user '{email}' already exists", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a StatDash user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--superuser", action="store_true", default=False)
    args = parser.parse_args()

    asyncio.run(create_user(args.email, args.password, args.superuser))
