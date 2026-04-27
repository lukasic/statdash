import asyncio
import subprocess

from sqlalchemy import inspect as sa_inspect

import app.models  # noqa: F401 — registers all models with Base.metadata
from app.core.database import create_db_and_tables, engine


async def main() -> None:
    async with engine.connect() as conn:
        has_alembic = await conn.run_sync(
            lambda c: sa_inspect(c).has_table("alembic_version")
        )

    if has_alembic:
        print("Existing database — running pending migrations")
        subprocess.run(["alembic", "upgrade", "head"], check=True)
    else:
        print("Fresh database — creating schema and stamping migrations")
        await create_db_and_tables()
        subprocess.run(["alembic", "stamp", "head"], check=True)


if __name__ == "__main__":
    asyncio.run(main())
