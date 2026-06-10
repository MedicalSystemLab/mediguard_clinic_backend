from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.app.models.auth import AuthPermissionEnum, User
from clinical_manage.app.models.info import PatientProfile
from clinical_manage.app.models.manage import FavoritePatient, Manage
from common.core.auth import TokenPayload, get_current_user_payload
from common.db.session import get_db

router = APIRouter()


class FavoritePatientResponse(BaseModel):
    patient_id: UUID
    patient_name: str
    gender: str
    birth: str
    department_id: UUID | None = None
    admitted_ward_id: UUID | None = None
    manage_practitioner_id: UUID | None = None
    created_at: str


async def get_current_user(
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
    return user


async def ensure_patient_access(
        *,
        db: AsyncSession,
        user: User,
        patient_id: UUID,
) -> PatientProfile:
    patient_result = await db.execute(
        select(PatientProfile).where(PatientProfile.patient_id == patient_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="환자를 찾을 수 없습니다.",
        )

    if user.permissions == AuthPermissionEnum.administrator:
        return patient

    manage_result = await db.execute(
        select(Manage).where(
            Manage.practitioner_id == user.user_id,
            Manage.patient_id == patient_id,
        )
    )
    if manage_result.scalar_one_or_none() is not None:
        return patient

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="해당 환자에 대한 접근 권한이 없습니다.",
    )


def to_response(favorite: FavoritePatient, patient: PatientProfile) -> FavoritePatientResponse:
    return FavoritePatientResponse(
        patient_id=patient.patient_id,
        patient_name=patient.patient_name,
        gender=patient.gender.value,
        birth=patient.birth,
        department_id=patient.department_id,
        admitted_ward_id=patient.admitted_ward_id,
        manage_practitioner_id=patient.manage_practitioner_id,
        created_at=favorite.created_at.isoformat(),
    )


@router.get("", response_model=list[FavoritePatientResponse], status_code=status.HTTP_200_OK)
async def read_favorite_patients(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
):
    user = await get_current_user(db, token_payload)
    result = await db.execute(
        select(FavoritePatient, PatientProfile)
        .join(PatientProfile, FavoritePatient.patient_id == PatientProfile.patient_id)
        .where(FavoritePatient.practitioner_id == user.user_id)
        .order_by(FavoritePatient.created_at.desc())
    )
    return [to_response(favorite, patient) for favorite, patient in result.all()]


@router.post("/{patient_id}", response_model=FavoritePatientResponse, status_code=status.HTTP_201_CREATED)
async def add_favorite_patient(
        *,
        patient_id: UUID,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
):
    user = await get_current_user(db, token_payload)
    patient = await ensure_patient_access(db=db, user=user, patient_id=patient_id)

    existing_result = await db.execute(
        select(FavoritePatient).where(
            FavoritePatient.practitioner_id == user.user_id,
            FavoritePatient.patient_id == patient_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return to_response(existing, patient)

    favorite = FavoritePatient(practitioner_id=user.user_id, patient_id=patient_id)
    db.add(favorite)
    await db.commit()
    await db.refresh(favorite)
    return to_response(favorite, patient)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_favorite_patient(
        *,
        patient_id: UUID,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
):
    user = await get_current_user(db, token_payload)
    result = await db.execute(
        select(FavoritePatient).where(
            FavoritePatient.practitioner_id == user.user_id,
            FavoritePatient.patient_id == patient_id,
        )
    )
    favorite = result.scalar_one_or_none()
    if favorite is None:
        return

    await db.delete(favorite)
    await db.commit()
