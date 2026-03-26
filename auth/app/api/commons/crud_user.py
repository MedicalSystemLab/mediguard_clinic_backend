from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ...models.auth import User
from ...schemas.auth import Register
from common.core.security import get_password_hash, get_email_hash, encrypt_data
# from common.core.nickname import generate_random_nickname

class CRUDUser:
    def get_email_hash_only(self, email: str) -> str:
        return get_email_hash(email)

    async def get(self, db: AsyncSession, id: Any) -> User | None:
        result = await db.execute(select(User).where(User.user_id == id))
        return result.scalars().first()

    async def get_by_email(self, db: AsyncSession, *, email: str) -> User | None:
        email_hash = self.get_email_hash_only(email)
        result = await db.execute(select(User).where(User.email_hash == email_hash))
        return result.scalars().first()

    async def create(self, db: AsyncSession, *, obj_in: Register) -> User:
        db_obj = User(
            email_hash=self.get_email_hash_only(obj_in.email),
            email_enc=encrypt_data(obj_in.email),
            password_hash=get_password_hash(obj_in.password),
            is_active=True # 기본적으로 비활성화 상태로 설정 (이메일 인증 후 active 상태로 전환)
        )
        db.add(db_obj)
        await db.flush() # user_id 생성을 위해 flush
        
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

user = CRUDUser()