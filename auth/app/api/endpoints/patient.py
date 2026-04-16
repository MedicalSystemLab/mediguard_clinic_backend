from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from common.core.security import verify_password, create_patient_refresh_token, create_patient_access_token
from common.core.config import settings
from common.core.kafka_producer import publish_event
from common.db.session import get_db
from common.schemas.events import PatientRegisteredEvent
from common.core.auth import get_current_patient_id
from auth.app.schemas.auth import Token, PatientLogin, PatientRegister
from auth.app.api.commons.crud_user import user as crud_user
from auth.app.schemas.auth import Patient as PatientSchema

router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
        *,
        db: AsyncSession = Depends(get_db),
        user_in: PatientRegister,
):
    user = await crud_user.get_by_username(db, username=user_in.username)

    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이 환자 번호로 등록된 사용자가 이미 존재합니다.",
        )

    # Publish user.registered event to Kafka
    event = PatientRegisteredEvent(
        patient_number=user_in.patient_number,
        patient_name=user_in.patient_name,
        patient_password=user_in.patient_password,
        patient_sex=user_in.patient_sex,

    )
    await publish_event(
        topic=settings.KAFKA_TOPIC_AUTH,
        event=event.model_dump(),
        key=user_in.patient_number
    )

    return


@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
async def patient_login(
        *,
        db: AsyncSession = Depends(get_db),
        login_in: PatientLogin,
):
    patient = await crud_user.get_by_username(db, username=login_in.patient_number)

    if not patient or not verify_password(login_in.patient_password, patient.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="환자 번호 또는 생년월일이 올바르지 않습니다.",
        )

    patient_id = patient.patient_id

    data = {
        "PatientId" : patient_id
    }

    return {
        "access_token": create_patient_access_token(data),
        "refresh_token": create_patient_refresh_token(data),
        "token_type": "bearer",
    }

@router.get("/me", response_model=PatientSchema, status_code=status.HTTP_200_OK)
async def read_user_me(
        patient_id: str = Depends(get_current_patient_id),
        db: AsyncSession = Depends(get_db)
):
    """
    현재 로그인된 사용자 정보 가져오기 (자동 로그인용)
    """
    user = await crud_user.get(db, id=patient_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return PatientSchema(user_id=user.user_id)