import os

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://gst_user:gst_password@localhost:5432/gst_itc"
)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)


async def init_db():
    """Create missing tables. Runs once when the app starts."""
    from gst_input_tax_credit_recovery_agent import models

    async with engine.begin() as conn:
        await conn.run_sync(models.SQLModel.metadata.create_all)


async def get_session():
    """FastAPI dependency: one database session per request."""
    async with AsyncSession(engine) as session:
        yield session
