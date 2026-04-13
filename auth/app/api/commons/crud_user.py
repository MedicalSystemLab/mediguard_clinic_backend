from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ...models.auth import User
from ...schemas.auth import Register
from common.core.security import get_password_hash

class CRUDUser:
    async def get(self, db: AsyncSession, id: Any) -> User | None:
        result = await db.execute(select(User).where(User.user_id == id))
        return result.scalars().first()

    async def get_by_username(self, db: AsyncSession, *, username: str) -> User | None:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalars().first()

    async def create(self, db: AsyncSession, *, obj_in: Register) -> User:
        db_obj = User(
            username=obj_in.username,
            password_hash=get_password_hash(obj_in.password),
            is_active=True
        )
        db.add(db_obj)
        await db.flush()  # user_id 생성을 위해 flush

        await db.commit()
        await db.refresh(db_obj)
        return db_obj

user = CRUDUser()