from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from clinical_manage.app.api.endpoints.admin_practitioner import get_current_admin, get_current_admin_or_practitioner
from clinical_manage.app.models.info import Department, PractitionerProfiles
from common.core.auth import TokenPayload, get_current_user_payload
from common.db.session import get_db

router = APIRouter()


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    department_name: str = Field(alias="name")
    department_en_name: str = Field(alias="enName")
    department_code: str = Field(alias="code")
    department_manager_id: UUID | None = Field(default=None, alias="headPractitioner")


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    department_name: str | None = Field(default=None, alias="name")
    department_en_name: str | None = Field(default=None, alias="enName")
    department_code: str | None = Field(default=None, alias="code")
    department_manager_id: UUID | None = Field(default=None, alias="headPractitioner")


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: UUID
    department_name: str
    department_en_name: str
    department_code: str
    department_manager_id: UUID | None = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


async def ensure_department_manager_exists(
    db: AsyncSession,
    department_manager_id: UUID | None,
) -> None:
    if department_manager_id is None:
        return

    result = await db.execute(
        select(PractitionerProfiles).where(
            PractitionerProfiles.practitioner_id == department_manager_id,
            PractitionerProfiles.is_deleted.is_(False),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부서 관리자를 찾을 수 없습니다.",
        )


async def get_department_or_404(
    *,
    db: AsyncSession,
    department_id: UUID,
    include_deleted: bool = False,
) -> Department:
    conditions = [Department.department_id == department_id]
    if not include_deleted:
        conditions.append(Department.is_deleted.is_(False))

    result = await db.execute(select(Department).where(*conditions))
    department = result.scalar_one_or_none()
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부서를 찾을 수 없습니다.",
        )

    return department


@router.get("", response_model=list[DepartmentResponse], status_code=status.HTTP_200_OK)
async def read_departments(
    *,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
    include_deleted: bool = Query(False),
):
    await get_current_admin_or_practitioner(db=db, token_payload=token_payload)

    conditions = []
    if not include_deleted:
        conditions.append(Department.is_deleted.is_(False))

    result = await db.execute(
        select(Department)
        .where(*conditions)
        .order_by(Department.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{department_id}", response_model=DepartmentResponse, status_code=status.HTTP_200_OK)
async def read_department(
    *,
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin_or_practitioner(db=db, token_payload=token_payload)
    return await get_department_or_404(db=db, department_id=department_id)


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    *,
    department_in: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    await ensure_department_manager_exists(db, department_in.department_manager_id)

    department = Department(**department_in.model_dump(), is_deleted=False)
    db.add(department)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="부서 이름, 영문 이름, 코드 중 이미 사용 중인 값이 있습니다.",
        ) from exc

    await db.refresh(department)
    return department


@router.patch("/{department_id}", response_model=DepartmentResponse, status_code=status.HTTP_200_OK)
async def update_department(
    *,
    department_id: UUID,
    department_in: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    department = await get_department_or_404(db=db, department_id=department_id)

    update_data = department_in.model_dump(exclude_unset=True)
    if "department_manager_id" in update_data:
        await ensure_department_manager_exists(db, department_in.department_manager_id)

    for field, value in update_data.items():
        setattr(department, field, value)
    department.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="부서 이름, 영문 이름, 코드 중 이미 사용 중인 값이 있습니다.",
        ) from exc

    await db.refresh(department)
    return department


@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    *,
    department_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    department = await get_department_or_404(db=db, department_id=department_id)

    department.is_deleted = True
    department.updated_at = datetime.now(timezone.utc)
    await db.commit()
