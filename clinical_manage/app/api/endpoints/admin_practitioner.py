from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.app.models.auth import AuthPermissionEnum, User
from clinical_manage.app.models.info import (
    Department,
    PractitionerProfiles,
    PractitionerRoleEnum,
)
from common.core.auth import TokenPayload, get_current_user_payload
from common.core.security import get_password_hash
from common.db.session import get_db

router = APIRouter()


class PractitionerCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    username: str = Field(alias="employeeId")
    password: str = Field(alias="tempPassword")
    practitioner_name: str = Field(alias="name")
    practitioner_en_name: str = Field(alias="enName")
    license_number: str = Field(alias="license")
    rule: PractitionerRoleEnum = Field(default=PractitionerRoleEnum.UNSPECIFIED, alias="role")
    department_id: UUID | None = Field(default=None, alias="dept")
    permissions: AuthPermissionEnum = AuthPermissionEnum.practitioner


class PractitionerUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    username: str | None = Field(default=None, alias="employeeId")
    password: str | None = Field(default=None, alias="tempPassword")
    practitioner_name: str | None = Field(default=None, alias="name")
    practitioner_en_name: str | None = Field(default=None, alias="enName")
    license_number: str | None = Field(default=None, alias="license")
    rule: PractitionerRoleEnum | None = Field(default=None, alias="role")
    department_id: UUID | None = Field(default=None, alias="dept")
    is_active: bool | None = None
    permissions: AuthPermissionEnum | None = None


class PractitionerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    practitioner_id: UUID
    username: str
    permissions: AuthPermissionEnum
    is_active: bool
    practitioner_name: str
    practitioner_en_name: str
    rule: PractitionerRoleEnum
    license_number: str
    department_id: UUID | None = None
    is_deleted: bool
    created_at: datetime


async def get_current_admin(
    *,
    db: AsyncSession,
    token_payload: TokenPayload,
) -> User:
    result = await db.execute(select(User).where(User.user_id == token_payload.sub))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없거나 비활성화된 계정입니다.",
        )

    if user.permissions != AuthPermissionEnum.administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )

    return user


async def get_current_admin_or_practitioner(
    *,
    db: AsyncSession,
    token_payload: TokenPayload,
) -> User:
    result = await db.execute(select(User).where(User.user_id == token_payload.sub))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없거나 비활성화된 계정입니다.",
        )

    if user.permissions not in {
        AuthPermissionEnum.administrator,
        AuthPermissionEnum.practitioner,
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 또는 의료진 권한이 필요합니다.",
        )

    return user


async def ensure_department_exists(db: AsyncSession, department_id: UUID | None) -> None:
    if department_id is None:
        return

    result = await db.execute(
        select(Department).where(
            Department.department_id == department_id,
            Department.is_deleted.is_(False),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="부서를 찾을 수 없습니다.",
        )


def to_response(user: User, profile: PractitionerProfiles) -> PractitionerResponse:
    return PractitionerResponse(
        practitioner_id=profile.practitioner_id,
        username=user.username,
        permissions=user.permissions,
        is_active=user.is_active,
        practitioner_name=profile.practitioner_name,
        practitioner_en_name=profile.practitioner_en_name,
        rule=profile.rule,
        license_number=profile.license_number,
        department_id=profile.department_id,
        is_deleted=profile.is_deleted,
        created_at=profile.created_at,
    )


async def get_practitioner_or_404(
    *,
    db: AsyncSession,
    practitioner_id: UUID,
    include_deleted: bool = False,
) -> tuple[User, PractitionerProfiles]:
    conditions = [PractitionerProfiles.practitioner_id == practitioner_id]
    if not include_deleted:
        conditions.append(PractitionerProfiles.is_deleted.is_(False))

    result = await db.execute(
        select(User, PractitionerProfiles)
        .join(PractitionerProfiles, PractitionerProfiles.practitioner_id == User.user_id)
        .where(*conditions)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="의료진을 찾을 수 없습니다.",
        )

    return row


@router.get("", response_model=list[PractitionerResponse], status_code=status.HTTP_200_OK)
async def read_practitioners(
    *,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
    include_deleted: bool = Query(False),
):
    await get_current_admin_or_practitioner(db=db, token_payload=token_payload)

    conditions = []
    if not include_deleted:
        conditions.append(PractitionerProfiles.is_deleted.is_(False))

    result = await db.execute(
        select(User, PractitionerProfiles)
        .join(PractitionerProfiles, PractitionerProfiles.practitioner_id == User.user_id)
        .where(*conditions)
        .order_by(PractitionerProfiles.created_at.desc())
    )
    return [to_response(user, profile) for user, profile in result.all()]


@router.get("/{practitioner_id}", response_model=PractitionerResponse, status_code=status.HTTP_200_OK)
async def read_practitioner(
    *,
    practitioner_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin_or_practitioner(db=db, token_payload=token_payload)
    user, profile = await get_practitioner_or_404(db=db, practitioner_id=practitioner_id)
    return to_response(user, profile)


@router.post("", response_model=PractitionerResponse, status_code=status.HTTP_201_CREATED)
async def create_practitioner(
    *,
    practitioner_in: PractitionerCreate,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    await ensure_department_exists(db, practitioner_in.department_id)

    existing_user_result = await db.execute(
        select(User).where(User.username == practitioner_in.username)
    )
    if existing_user_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이 사용자명으로 등록된 사용자가 이미 존재합니다.",
        )

    user = User(
        username=practitioner_in.username,
        password_hash=get_password_hash(practitioner_in.password),
        permissions=practitioner_in.permissions,
        is_active=True,
        is_reset_password=True,
    )
    db.add(user)
    await db.flush()

    profile = PractitionerProfiles(
        practitioner_id=user.user_id,
        practitioner_name=practitioner_in.practitioner_name,
        practitioner_en_name=practitioner_in.practitioner_en_name,
        rule=practitioner_in.rule,
        license_number=practitioner_in.license_number,
        department_id=practitioner_in.department_id,
        is_deleted=False,
    )
    db.add(profile)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="의료진 이름, 영문 이름, 면허번호 중 이미 사용 중인 값이 있습니다.",
        ) from exc

    await db.refresh(user)
    await db.refresh(profile)
    return to_response(user, profile)


@router.patch("/{practitioner_id}", response_model=PractitionerResponse, status_code=status.HTTP_200_OK)
async def update_practitioner(
    *,
    practitioner_id: UUID,
    practitioner_in: PractitionerUpdate,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    user, profile = await get_practitioner_or_404(db=db, practitioner_id=practitioner_id)

    update_data = practitioner_in.model_dump(exclude_unset=True)
    if "department_id" in update_data:
        await ensure_department_exists(db, practitioner_in.department_id)

    if practitioner_in.username is not None and practitioner_in.username != user.username:
        existing_user_result = await db.execute(
            select(User).where(User.username == practitioner_in.username)
        )
        if existing_user_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이 사용자명으로 등록된 사용자가 이미 존재합니다.",
            )
        user.username = practitioner_in.username

    if practitioner_in.password is not None:
        user.password_hash = get_password_hash(practitioner_in.password)
        user.is_reset_password = True
    if practitioner_in.is_active is not None:
        user.is_active = practitioner_in.is_active
    if practitioner_in.permissions is not None:
        user.permissions = practitioner_in.permissions

    for field in (
        "practitioner_name",
        "practitioner_en_name",
        "license_number",
        "rule",
        "department_id",
    ):
        if field in update_data:
            setattr(profile, field, getattr(practitioner_in, field))

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="의료진 이름, 영문 이름, 면허번호 중 이미 사용 중인 값이 있습니다.",
        ) from exc

    await db.refresh(user)
    await db.refresh(profile)
    return to_response(user, profile)


@router.delete("/{practitioner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_practitioner(
    *,
    practitioner_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    user, profile = await get_practitioner_or_404(db=db, practitioner_id=practitioner_id)

    profile.is_deleted = True
    user.is_active = False
    await db.commit()
