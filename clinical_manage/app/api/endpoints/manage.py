from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, status, Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from auth.app.models.auth import User
from auth.app.models.auth import Patient
from clinical_manage.app.models.info import PatientProfile, PractitionerProfiles
from clinical_manage.app.models.manage import AlertConfig
from common.db.session import get_db
from common.core.config import settings
from common.core.auth import TokenPayload, get_current_patient_id, get_current_user_payload
from common.core.kafka_producer import publish_event


router = APIRouter()
security = HTTPBearer()
ALERT_PAUSE_FIELDS = {
    "bpm_alert_paused_until",
    "spo2_alert_paused_until",
    "rr_alert_paused_until",
    "bp_alert_paused_until",
    "temp_alert_paused_until",
}


class AlertConfigResponse(BaseModel):
    patient_id: UUID
    bpm_max: int
    bpm_min: int
    bpm_alert_paused_until: datetime | None = None
    spo2_max: int
    spo2_min: int
    spo2_alert_paused_until: datetime | None = None
    rr_max: int
    rr_min: int
    rr_alert_paused_until: datetime | None = None
    bp_max: int
    bp_min: int
    bp_alert_paused_until: datetime | None = None
    temp_max: int
    temp_min: int
    temp_alert_paused_until: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertConfigUpdate(BaseModel):
    bpm_max: int | None = None
    bpm_min: int | None = None
    bpm_alert_paused_until: datetime | None = None
    spo2_max: int | None = None
    spo2_min: int | None = None
    spo2_alert_paused_until: datetime | None = None
    rr_max: int | None = None
    rr_min: int | None = None
    rr_alert_paused_until: datetime | None = None
    bp_max: int | None = None
    bp_min: int | None = None
    bp_alert_paused_until: datetime | None = None
    temp_max: int | None = None
    temp_min: int | None = None
    temp_alert_paused_until: datetime | None = None


def get_patient_id_from_access_token(token_payload: TokenPayload) -> UUID:
    if token_payload.type != "access" or token_payload.permissions != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="환자 AccessToken만 사용할 수 있습니다.",
        )

    try:
        return UUID(token_payload.sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 환자 토큰입니다.",
        ) from exc


async def get_or_create_alert_config(db: AsyncSession, patient_id: UUID) -> AlertConfig:
    result = await db.execute(select(AlertConfig).where(AlertConfig.patient_id == patient_id))
    alert_config = result.scalar_one_or_none()
    if alert_config is not None:
        return alert_config

    alert_config = AlertConfig(patient_id=patient_id)
    db.add(alert_config)
    await db.flush()
    await db.refresh(alert_config)
    return alert_config


@router.get("/profile", status_code=status.HTTP_200_OK)
async def get_profile(
    *,
    current_client_id: str = Depends(get_current_patient_id),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.user_id == current_client_id))
    user = result.scalar_one_or_none()

    if user:
        return {"client_id": current_client_id, "type": "user", "user": user}

    result = await db.execute(select(Patient).where(Patient.patient_id == current_client_id))
    user = result.scalar_one_or_none()

    if user:
        profile_result = await db.execute(select(PatientProfile).where(PatientProfile.patient_id == current_client_id))
        profile = profile_result.scalar_one_or_none()
        
        if profile:
            return {"client_id": current_client_id, "type": "patient", "profile": profile}


    return {"message": "Not Found Profile", "client_id": current_client_id}


@router.get("/alert/config", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def read_alert_config(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
):
    patient_id = get_patient_id_from_access_token(token_payload)
    alert_config = await get_or_create_alert_config(db, patient_id)
    response = AlertConfigResponse.model_validate(alert_config)
    await db.commit()

    return response


@router.patch("/alert/config", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def update_alert_config(
        *,
        alert_config_in: AlertConfigUpdate,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
):
    patient_id = get_patient_id_from_access_token(token_payload)
    update_data = alert_config_in.model_dump(exclude_unset=True)
    invalid_null_fields = [
        field
        for field, value in update_data.items()
        if value is None and field not in ALERT_PAUSE_FIELDS
    ]
    if invalid_null_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"임계치 값은 null로 설정할 수 없습니다: {', '.join(invalid_null_fields)}",
        )

    alert_config = await get_or_create_alert_config(db, patient_id)
    for field, value in update_data.items():
        setattr(alert_config, field, value)
    alert_config.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(alert_config)
    response = AlertConfigResponse.model_validate(alert_config)
    await db.commit()

    return response
