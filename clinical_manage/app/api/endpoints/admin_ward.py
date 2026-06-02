from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from clinical_manage.app.api.endpoints.admin_practitioner import get_current_admin
from clinical_manage.app.models.info import Department, Ward
from common.core.auth import TokenPayload, get_current_user_payload
from common.db.session import get_db

router = APIRouter()


class WardCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ward_name: str = Field(alias="name", description="병동 명", examples=["중환자 병동"])
    ward_en_name: str = Field(alias="enName", description="영문 명칭", examples=["Intensive Care Ward"])
    ward_code: str = Field(alias="code", description="병동 코드. 유니크 값입니다.", examples=["ICU-01"])
    ward_manage_department_id: UUID | None = Field(
        default=None,
        alias="dept",
        description="소속 부서 ID. department.department_id UUID 문자열입니다.",
        examples=["9f3b1c9c-7b72-44b2-9c23-60e6996ce6d1"],
    )
    ward_bed_count: int = Field(default=0, ge=0, alias="beds", description="병상 수", examples=[20])
    ward_loc: str = Field(alias="loc", description="위치", examples=["본관 3층"])


class WardUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ward_name: str | None = Field(default=None, alias="name", description="병동 명")
    ward_en_name: str | None = Field(default=None, alias="enName", description="영문 명칭")
    ward_code: str | None = Field(default=None, alias="code", description="병동 코드. 유니크 값입니다.")
    ward_manage_department_id: UUID | None = Field(
        default=None,
        alias="dept",
        description="소속 부서 ID. department.department_id UUID 문자열입니다.",
    )
    ward_bed_count: int | None = Field(default=None, ge=0, alias="beds", description="병상 수")
    ward_loc: str | None = Field(default=None, alias="loc", description="위치")


class WardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    ward_id: UUID = Field(alias="id", description="병동 ID")
    ward_name: str = Field(alias="name", description="병동 명")
    ward_en_name: str = Field(alias="enName", description="영문 명칭")
    ward_code: str = Field(alias="code", description="병동 코드")
    ward_manage_department_id: str | None = Field(default=None, alias="dept", description="소속 부서 ID")
    ward_bed_count: int = Field(alias="beds", description="병상 수")
    ward_loc: str = Field(alias="loc", description="위치")
    is_deleted: bool = Field(description="삭제 여부")
    created_at: datetime = Field(description="생성 일시")
    updated_at: datetime = Field(description="수정 일시")

    @field_validator("ward_manage_department_id", mode="before")
    @classmethod
    def stringify_department_id(cls, value: UUID | str | None) -> str | None:
        if value is None:
            return None
        return str(value)


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


async def get_ward_or_404(
    *,
    db: AsyncSession,
    ward_id: UUID,
    include_deleted: bool = False,
) -> Ward:
    conditions = [Ward.ward_id == ward_id]
    if not include_deleted:
        conditions.append(Ward.is_deleted.is_(False))

    result = await db.execute(select(Ward).where(*conditions))
    ward = result.scalar_one_or_none()
    if ward is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="병동을 찾을 수 없습니다.",
        )

    return ward


@router.get(
    "",
    response_model=list[WardResponse],
    status_code=status.HTTP_200_OK,
    summary="병동 목록 조회",
    description=(
        "관리자 권한으로 병동 목록을 조회합니다. 기본적으로 삭제 처리되지 않은 병동만 반환하며, "
        "`include_deleted=true`를 지정하면 삭제된 병동도 함께 조회합니다."
    ),
)
async def read_wards(
    *,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
    include_deleted: bool = Query(False),
):
    await get_current_admin(db=db, token_payload=token_payload)

    conditions = []
    if not include_deleted:
        conditions.append(Ward.is_deleted.is_(False))

    result = await db.execute(
        select(Ward)
        .where(*conditions)
        .order_by(Ward.created_at.desc())
    )
    return result.scalars().all()


@router.get(
    "/{ward_id}",
    response_model=WardResponse,
    status_code=status.HTTP_200_OK,
    summary="병동 상세보기",
    description="관리자 권한으로 병동 ID에 해당하는 병동 상세 정보를 조회합니다.",
)
async def read_ward(
    *,
    ward_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    return await get_ward_or_404(db=db, ward_id=ward_id)


@router.post(
    "",
    response_model=WardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="병동 생성",
    description=(
        "`name`, `enName`, `code`, `dept`, `beds`, `loc` 형식으로 병동을 생성합니다. "
        "`code`는 유니크해야 하며, `dept`가 전달되면 존재하는 부서 ID인지 검증합니다."
    ),
)
async def create_ward(
    *,
    ward_in: WardCreate,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    await ensure_department_exists(db, ward_in.ward_manage_department_id)

    ward = Ward(**ward_in.model_dump(), is_deleted=False)
    db.add(ward)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="병동 이름, 영문 이름, 코드 중 이미 사용 중인 값이 있습니다.",
        ) from exc

    await db.refresh(ward)
    return ward


@router.patch(
    "/{ward_id}",
    response_model=WardResponse,
    status_code=status.HTTP_200_OK,
    summary="병동 수정",
    description=(
        "병동 ID에 해당하는 병동 정보를 부분 수정합니다. 요청 본문에는 변경할 필드만 포함하면 됩니다. "
        "`dept`가 전달되면 존재하는 부서 ID인지 검증합니다."
    ),
)
async def update_ward(
    *,
    ward_id: UUID,
    ward_in: WardUpdate,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    ward = await get_ward_or_404(db=db, ward_id=ward_id)

    update_data = ward_in.model_dump(exclude_unset=True)
    if "ward_manage_department_id" in update_data:
        await ensure_department_exists(db, ward_in.ward_manage_department_id)

    for field, value in update_data.items():
        setattr(ward, field, value)
    ward.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="병동 이름, 영문 이름, 코드 중 이미 사용 중인 값이 있습니다.",
        ) from exc

    await db.refresh(ward)
    return ward


@router.delete(
    "/{ward_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="병동 삭제",
    description="병동을 물리 삭제하지 않고 `is_deleted=true`로 변경하는 소프트 삭제를 수행합니다.",
)
async def delete_ward(
    *,
    ward_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    ward = await get_ward_or_404(db=db, ward_id=ward_id)

    ward.is_deleted = True
    ward.updated_at = datetime.now(timezone.utc)
    await db.commit()
