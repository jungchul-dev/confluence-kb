from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def ensure_schema() -> None:
    """확장은 db/init.sql 이, 테이블·인덱스는 여기서 만든다. API 서버와 워커 둘 다 기동 시 호출한다."""
    from app.db import models  # noqa: F401  (metadata 등록)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
