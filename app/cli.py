"""Management commands.

python -m app.cli create-admin --email admin@example.com --name Admin
python -m app.cli seed     # demo data for local development
"""

import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.database import Database
from app.models import Comment, News, User

DEMO_PASSWORD = "Password123"  # noqa: S105 - demo data for local development only


async def create_admin(email: str, name: str, password: str) -> None:
    db = Database(get_settings().database_url)
    try:
        async with db.sessionmaker() as session:
            user = await session.scalar(select(User).where(User.email == email.lower()))
            if user is None:
                user = User(name=name, email=email.lower())
                session.add(user)
            user.hashed_password = hash_password(password)
            user.is_admin = True
            user.is_author = True
            await session.commit()
            print(f"Administrator {email} is ready.")
    finally:
        await db.dispose()


async def seed() -> None:
    db = Database(get_settings().database_url)
    try:
        async with db.sessionmaker() as session:
            if await session.scalar(select(User.id).limit(1)) is not None:
                print("Database is not empty, skipping seed.")
                return
            pw = hash_password(DEMO_PASSWORD)
            admin = User(
                name="Admin",
                email="admin@example.com",
                hashed_password=pw,
                is_admin=True,
                is_author=True,
            )
            author = User(
                name="Alice", email="alice@example.com", hashed_password=pw, is_author=True
            )
            reader = User(name="Bob", email="bob@example.com", hashed_password=pw)
            first = News(
                title="Welcome to the news portal",
                content={"body": "This is the first news article."},
                author=author,
            )
            second = News(
                title="Admin announcement",
                content={"body": "Comments are open for everyone."},
                author=admin,
            )
            session.add_all([admin, author, reader, first, second])
            await session.flush()
            session.add(Comment(text="Great first article!", news_id=first.id, author=reader))
            await session.commit()
            print(
                f"Seeded demo users (password: {DEMO_PASSWORD}): "
                "admin@example.com, alice@example.com, bob@example.com"
            )
    finally:
        await db.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="Create or promote an administrator")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="Admin")
    sub.add_parser("seed", help="Fill an empty database with demo data")
    args = parser.parse_args()

    if args.command == "create-admin":
        password = getpass.getpass("Password: ")
        if len(password) < 8:
            parser.error("password must be at least 8 characters")
        asyncio.run(create_admin(args.email, args.name, password))
    else:
        asyncio.run(seed())


if __name__ == "__main__":
    main()
