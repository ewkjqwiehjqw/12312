import asyncio
from sqlalchemy import text
from database import engine
from models import Base

async def migrate_database():
    """Migrate database to latest schema"""
    async with engine.begin() as conn:
        # Drop existing tables
        await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("Database migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(migrate_database()) 