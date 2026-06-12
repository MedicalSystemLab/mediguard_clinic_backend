from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, status, Depends, HTTPException, Header
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from auth.app.models.auth import AuthPermissionEnum, User
from auth.app.models.auth import Patient
from clinical_manage.app.models.info import PatientProfile, PractitionerProfiles
from clinical_manage.app.models.manage import AlertConfig
from common.db.session import get_db
from common.core.config import settings
from common.core.auth import TokenPayload, decode_authorization_payload, get_current_patient_id
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
ALERT_METRIC_PAUSE_FIELDS = {
    "bpm": ("bpm_alert_paused_until",),
    "resp": ("rr_alert_paused_until",),
    "spo2": ("spo2_alert_paused_until",),
    "temp": ("temp_alert_paused_until",),
    "bp": ("bp_alert_paused_until",),
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


async def get_current_patient_access_token_payload(
        authorization: str = Header(..., description="Bearer <patient access token>"),
) -> TokenPayload:
    token_payload = decode_authorization_payload(authorization)
    get_patient_id_from_access_token(token_payload)
    return token_payload


async def get_current_hospital_user(
        *,
        db: AsyncSession = Depends(get_db),
        authorization: str = Header(..., description="Bearer <hospital access token>"),
) -> User:
    token_payload = decode_authorization_payload(authorization)
    if token_payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="병원직원 AccessToken만 사용할 수 있습니다.",
        )

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
            detail="병원직원 권한이 필요합니다.",
        )

    return user


async def ensure_patient_exists(
        *,
        db: AsyncSession,
        patient_id: UUID,
) -> None:
    result = await db.execute(select(PatientProfile).where(PatientProfile.patient_id == patient_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="환자를 찾을 수 없습니다.",
        )


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


async def set_alert_pause_until(
        *,
        db: AsyncSession,
        token_payload: TokenPayload,
        pause_fields: tuple[str, ...],
        paused_until: datetime,
) -> AlertConfigResponse:
    patient_id = get_patient_id_from_access_token(token_payload)
    alert_config = await get_or_create_alert_config(db, patient_id)
    for field in pause_fields:
        setattr(alert_config, field, paused_until)
    alert_config.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(alert_config)
    response = AlertConfigResponse.model_validate(alert_config)
    await db.commit()
    return response


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
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    patient_id = get_patient_id_from_access_token(token_payload)
    alert_config = await get_or_create_alert_config(db, patient_id)
    response = AlertConfigResponse.model_validate(alert_config)
    await db.commit()

    return response


@router.get(
    "/alert/config/{patient_id}",
    response_model=AlertConfigResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_hospital_user)],
)
async def read_patient_alert_config(
        *,
        patient_id: UUID,
        db: AsyncSession = Depends(get_db),
):
    await ensure_patient_exists(db=db, patient_id=patient_id)
    alert_config = await get_or_create_alert_config(db, patient_id)
    response = AlertConfigResponse.model_validate(alert_config)
    await db.commit()

    return response


@router.post("/alert/disable", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def disable_all_alerts(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=tuple(ALERT_PAUSE_FIELDS),
        paused_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )


@router.post("/alert/disable/bpm", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def disable_bpm_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["bpm"],
        paused_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )


@router.post("/alert/disable/resp", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def disable_resp_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["resp"],
        paused_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )


@router.post("/alert/disable/spo2", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def disable_spo2_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["spo2"],
        paused_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )


@router.post("/alert/disable/temp", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def disable_temp_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["temp"],
        paused_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )


@router.post("/alert/disable/bp", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def disable_bp_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["bp"],
        paused_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )


@router.post("/alert/enable", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def enable_all_alerts(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=tuple(ALERT_PAUSE_FIELDS),
        paused_until=datetime.now(timezone.utc),
    )


@router.post("/alert/enable/bpm", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def enable_bpm_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["bpm"],
        paused_until=datetime.now(timezone.utc),
    )


@router.post("/alert/enable/resp", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def enable_resp_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["resp"],
        paused_until=datetime.now(timezone.utc),
    )


@router.post("/alert/enable/spo2", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def enable_spo2_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["spo2"],
        paused_until=datetime.now(timezone.utc),
    )


@router.post("/alert/enable/temp", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def enable_temp_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["temp"],
        paused_until=datetime.now(timezone.utc),
    )


@router.post("/alert/enable/bp", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def enable_bp_alert(
        *,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
):
    return await set_alert_pause_until(
        db=db,
        token_payload=token_payload,
        pause_fields=ALERT_METRIC_PAUSE_FIELDS["bp"],
        paused_until=datetime.now(timezone.utc),
    )


@router.patch("/alert/config", response_model=AlertConfigResponse, status_code=status.HTTP_200_OK)
async def update_alert_config(
        *,
        alert_config_in: AlertConfigUpdate,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_patient_access_token_payload),
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
