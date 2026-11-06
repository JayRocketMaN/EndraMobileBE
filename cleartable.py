import asyncio
from sqlalchemy import text
from app.core.database import AsyncSessionLocal  # Adjust to your session maker name if different


async def truncate_all_tables():
    """Dynamically truncates all tables in the current schema and resets primary key sequences."""
    truncate_query = """
    DO $$ 
    DECLARE
        r RECORD;
    BEGIN
        FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = current_schema()) LOOP
            EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE;';
        END LOOP;
    END $$;
    """
    
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(text(truncate_query))
        print("Successfully truncated all database tables and reset identity sequences.")


if __name__ == "__main__":
    asyncio.run(truncate_all_tables())