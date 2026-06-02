from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.app.models.auth import AuthPermissionEnum, Patient, User
from clinical_manage.app.models.info import (
    Department,
    GenderEnum,
    PatientProfile,
    PractitionerProfiles,
    Ward,
)
from common.core.auth import TokenPayload, get_current_user_payload
from common.core.security import get_password_hash
from common.db.session import get_db

router = APIRouter()


class PatientCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    patient_number: str = Field(alias="number", description="환자 번호. 로그인 ID로 사용되며 유니크 값입니다.")
    patient_name: str = Field(alias="name", description="환자 이름")
    birth: str = Field(description="생년월일. 환자 초기 로그인 비밀번호로 사용됩니다.")
    gender: GenderEnum = Field(default=GenderEnum.U, description="성별")
    department_id: UUID | None = Field(default=None, alias="depart", description="진료 부서 ID")
    admitted_ward_id: UUID | None = Field(
        default=None,
        alias="admittedWard",
        validation_alias=AliasChoices("admittedWard", "admitted_ward"),
        description="입원 병동 ID",
    )
    manage_practitioner_id: UUID | None = Field(
        default=None,
        alias="managePractitioner",
        validation_alias=AliasChoices("managePractitioner", "manage_practitioner"),
        description="담당 의료진 ID",
    )
    is_admitted: bool = Field(default=True, alias="isAdmitted", description="입원 여부")


class PatientUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    patient_number: str | None = Field(default=None, alias="number", description="환자 번호")
    patient_name: str | None = Field(default=None, alias="name", description="환자 이름")
    birth: str | None = Field(default=None, description="생년월일. 변경 시 환자 로그인 비밀번호도 함께 변경됩니다.")
    gender: GenderEnum | None = Field(default=None, description="성별")
    department_id: UUID | None = Field(default=None, alias="depart", description="진료 부서 ID")
    admitted_ward_id: UUID | None = Field(
        default=None,
        alias="admittedWard",
        validation_alias=AliasChoices("admittedWard", "admitted_ward"),
        description="입원 병동 ID",
    )
    manage_practitioner_id: UUID | None = Field(
        default=None,
        alias="managePractitioner",
        validation_alias=AliasChoices("managePractitioner", "manage_practitioner"),
        description="담당 의료진 ID",
    )
    is_admitted: bool | None = Field(default=None, alias="isAdmitted", description="입원 여부")
    is_active: bool | None = Field(default=None, alias="isActive", description="환자 로그인 계정 활성 여부")


class PatientResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    patient_id: UUID = Field(alias="id", description="환자 ID")
    patient_number: str = Field(alias="number", description="환자 번호")
    is_active: bool = Field(alias="isActive", description="환자 로그인 계정 활성 여부")
    patient_name: str = Field(alias="name", description="환자 이름")
    birth: str = Field(description="생년월일")
    gender: GenderEnum = Field(description="성별")
    department_id: str | None = Field(default=None, alias="depart", description="진료 부서 ID")
    admitted_ward_id: str | None = Field(default=None, alias="admittedWard", description="입원 병동 ID")
    manage_practitioner_id: str | None = Field(
        default=None,
        alias="managePractitioner",
        description="담당 의료진 ID",
    )
    is_admitted: bool = Field(alias="isAdmitted", description="입원 여부")
    created_at: datetime = Field(description="계정 생성 일시")
    profile_created_at: datetime = Field(alias="profileCreatedAt", description="프로필 생성 일시")
    discharged_at: datetime | None = Field(default=None, alias="dischargedAt", description="퇴원 일시")

    @field_validator("department_id", "admitted_ward_id", "manage_practitioner_id", mode="before")
    @classmethod
    def stringify_uuid(cls, value: UUID | str | None) -> str | None:
        if value is None:
            return None
        return str(value)


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


async def ensure_ward_exists(db: AsyncSession, ward_id: UUID | None) -> None:
    if ward_id is None:
        return

    result = await db.execute(
        select(Ward).where(
            Ward.ward_id == ward_id,
            Ward.is_deleted.is_(False),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="병동을 찾을 수 없습니다.",
        )


async def ensure_practitioner_exists(db: AsyncSession, practitioner_id: UUID | None) -> None:
    if practitioner_id is None:
        return

    result = await db.execute(
        select(PractitionerProfiles).where(
            PractitionerProfiles.practitioner_id == practitioner_id,
            PractitionerProfiles.is_deleted.is_(False),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="담당 의료진을 찾을 수 없습니다.",
        )


async def ensure_patient_refs_exist(
    db: AsyncSession,
    *,
    department_id: UUID | None,
    admitted_ward_id: UUID | None,
    manage_practitioner_id: UUID | None,
) -> None:
    await ensure_department_exists(db, department_id)
    await ensure_ward_exists(db, admitted_ward_id)
    await ensure_practitioner_exists(db, manage_practitioner_id)


async def get_patient_or_404(
    *,
    db: AsyncSession,
    patient_id: UUID,
    include_inactive: bool = False,
) -> tuple[Patient, PatientProfile]:
    conditions = [Patient.patient_id == patient_id]
    if not include_inactive:
        conditions.append(Patient.is_active.is_(True))

    result = await db.execute(
        select(Patient, PatientProfile)
        .join(PatientProfile, PatientProfile.patient_id == Patient.patient_id)
        .where(*conditions)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="환자를 찾을 수 없습니다.",
        )

    return row


def to_response(patient: Patient, profile: PatientProfile) -> PatientResponse:
    return PatientResponse(
        patient_id=patient.patient_id,
        patient_number=patient.patient_number,
        is_active=patient.is_active,
        patient_name=profile.patient_name,
        birth=profile.birth,
        gender=profile.gender,
        department_id=profile.department_id,
        admitted_ward_id=profile.admitted_ward_id,
        manage_practitioner_id=profile.manage_practitioner_id,
        is_admitted=profile.is_admitted,
        created_at=patient.created_at,
        profile_created_at=profile.created_at,
        discharged_at=profile.discharged_at,
    )


@router.get(
    "",
    response_model=list[PatientResponse],
    status_code=status.HTTP_200_OK,
    summary="환자 목록 조회",
    description=(
        "관리자 권한으로 환자 계정과 환자 프로필 목록을 조회합니다. "
        "기본적으로 활성 환자 계정만 반환하며, `include_inactive=true`를 지정하면 비활성 계정도 포함합니다."
    ),
)
async def read_patients(
    *,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
    include_inactive: bool = Query(False),
):
    await get_current_admin(db=db, token_payload=token_payload)

    conditions = []
    if not include_inactive:
        conditions.append(Patient.is_active.is_(True))

    result = await db.execute(
        select(Patient, PatientProfile)
        .join(PatientProfile, PatientProfile.patient_id == Patient.patient_id)
        .where(*conditions)
        .order_by(Patient.created_at.desc())
    )
    return [to_response(patient, profile) for patient, profile in result.all()]


@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    status_code=status.HTTP_200_OK,
    summary="환자 상세보기",
    description="관리자 권한으로 환자 ID에 해당하는 계정과 프로필 상세 정보를 조회합니다.",
)
async def read_patient(
    *,
    patient_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    patient, profile = await get_patient_or_404(db=db, patient_id=patient_id)
    return to_response(patient, profile)


@router.post(
    "",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="환자 생성",
    description=(
        "관리자 권한으로 환자 로그인 계정과 환자 프로필을 함께 생성합니다. "
        "`number`는 로그인 ID이며 유니크해야 하고, `birth`는 환자 초기 로그인 비밀번호로 해시 저장됩니다."
    ),
)
async def create_patient(
    *,
    patient_in: PatientCreate,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    await ensure_patient_refs_exist(
        db,
        department_id=patient_in.department_id,
        admitted_ward_id=patient_in.admitted_ward_id,
        manage_practitioner_id=patient_in.manage_practitioner_id,
    )

    existing_patient_result = await db.execute(
        select(Patient).where(Patient.patient_number == patient_in.patient_number)
    )
    if existing_patient_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이 환자 번호로 등록된 사용자가 이미 존재합니다.",
        )

    patient = Patient(
        patient_number=patient_in.patient_number,
        patient_password=get_password_hash(patient_in.birth),
        is_active=True,
    )
    db.add(patient)
    await db.flush()

    profile = PatientProfile(
        patient_id=patient.patient_id,
        patient_name=patient_in.patient_name,
        gender=patient_in.gender,
        birth=patient_in.birth,
        is_admitted=patient_in.is_admitted,
        department_id=patient_in.department_id,
        admitted_ward_id=patient_in.admitted_ward_id,
        manage_practitioner_id=patient_in.manage_practitioner_id,
        discharged_at=None if patient_in.is_admitted else datetime.now(timezone.utc),
    )
    db.add(profile)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="환자 번호로 등록된 사용자가 이미 존재하거나 환자 프로필이 중복되었습니다.",
        ) from exc

    await db.refresh(patient)
    await db.refresh(profile)
    return to_response(patient, profile)


@router.patch(
    "/{patient_id}",
    response_model=PatientResponse,
    status_code=status.HTTP_200_OK,
    summary="환자 수정",
    description=(
        "관리자 권한으로 환자 로그인 계정과 환자 프로필을 부분 수정합니다. "
        "`birth`를 변경하면 환자 로그인 비밀번호도 변경된 생년월일 기준으로 다시 해시 저장됩니다."
    ),
)
async def update_patient(
    *,
    patient_id: UUID,
    patient_in: PatientUpdate,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    patient, profile = await get_patient_or_404(db=db, patient_id=patient_id, include_inactive=True)

    update_data = patient_in.model_dump(exclude_unset=True)
    await ensure_patient_refs_exist(
        db,
        department_id=patient_in.department_id if "department_id" in update_data else None,
        admitted_ward_id=patient_in.admitted_ward_id if "admitted_ward_id" in update_data else None,
        manage_practitioner_id=patient_in.manage_practitioner_id if "manage_practitioner_id" in update_data else None,
    )

    if patient_in.patient_number is not None and patient_in.patient_number != patient.patient_number:
        existing_patient_result = await db.execute(
            select(Patient).where(Patient.patient_number == patient_in.patient_number)
        )
        if existing_patient_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이 환자 번호로 등록된 사용자가 이미 존재합니다.",
            )
        patient.patient_number = patient_in.patient_number

    if patient_in.birth is not None:
        profile.birth = patient_in.birth
        patient.patient_password = get_password_hash(patient_in.birth)
    if patient_in.is_active is not None:
        patient.is_active = patient_in.is_active

    for field in (
        "patient_name",
        "gender",
        "department_id",
        "admitted_ward_id",
        "manage_practitioner_id",
        "is_admitted",
    ):
        if field in update_data:
            setattr(profile, field, getattr(patient_in, field))

    if patient_in.is_admitted is True:
        profile.discharged_at = None
    elif patient_in.is_admitted is False and profile.discharged_at is None:
        profile.discharged_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="환자 번호로 등록된 사용자가 이미 존재하거나 환자 프로필이 중복되었습니다.",
        ) from exc

    await db.refresh(patient)
    await db.refresh(profile)
    return to_response(patient, profile)


@router.delete(
    "/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="환자 삭제",
    description=(
        "관리자 권한으로 환자 로그인을 비활성화하고 환자 프로필을 퇴원 상태로 변경합니다. "
        "물리 삭제는 수행하지 않습니다."
    ),
)
async def delete_patient(
    *,
    patient_id: UUID,
    db: AsyncSession = Depends(get_db),
    token_payload: TokenPayload = Depends(get_current_user_payload),
):
    await get_current_admin(db=db, token_payload=token_payload)
    patient, profile = await get_patient_or_404(db=db, patient_id=patient_id, include_inactive=True)

    patient.is_active = False
    profile.is_admitted = False
    if profile.discharged_at is None:
        profile.discharged_at = datetime.now(timezone.utc)

    await db.commit()
