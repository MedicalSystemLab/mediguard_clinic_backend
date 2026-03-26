import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from common.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL, 
    pool_pre_ping=True,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False)
)
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

async def get_db():
    async with SessionLocal() as session:
        yield session
