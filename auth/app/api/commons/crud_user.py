from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ...models.auth import User, Patient
from ...schemas.auth import UserRegister, PatientRegister
from common.core.security import get_password_hash

class CRUDUser:
    async def get(self, db: AsyncSession, id: Any) -> User | None:
        result = await db.execute(select(User).where(User.user_id == id))
        return result.scalars().first()

    async def get_by_username(self, db: AsyncSession, *, username: str) -> User | None:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalars().first()

    async def create(self, db: AsyncSession, *, obj_in: UserRegister) -> User:
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

class CRUDPatient:
    async def get(self, db: AsyncSession, id: Any) -> Patient | None:
        result = await db.execute(select(Patient).where(Patient.patient_id == id))
        return result.scalars().first()

    async def get_by_patient_number(self, db: AsyncSession, *, patient_number: str) -> Patient | None:
        result = await db.execute(select(Patient).where(Patient.patient_number == patient_number))
        return result.scalars().first()

    async def create(self, db: AsyncSession, *, obj_in: PatientRegister) -> Patient:
        db_obj = Patient(
            patient_number=obj_in.patient_number,
            patient_password=get_password_hash(obj_in.patient_password),
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj


user = CRUDUser()
patient = CRUDPatient()