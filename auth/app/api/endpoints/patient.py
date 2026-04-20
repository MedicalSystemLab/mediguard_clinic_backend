from fastapi import APIRouter, status, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from common.core.security import verify_password, create_patient_refresh_token, create_patient_access_token
from common.core.config import settings
from common.core.kafka_producer import publish_event
from common.db.session import get_db
from common.schemas.events import PatientRegisteredEvent
from common.core.auth import get_current_patient_id
from auth.app.schemas.auth import Token, PatientLogin, PatientRegister
from auth.app.api.commons.crud_user import patient as crud_patient
from auth.app.schemas.auth import Patient as PatientSchema
from auth.app.models.auth import User
from clinical_manage.app.models.info import Ward, Department


router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
        *,
        db: AsyncSession = Depends(get_db),
        patient_in: PatientRegister,
):
    user = await crud_patient.get_by_patient_number(db, patient_number=patient_in.number)

    if patient_in.depart:
        depart = db.query(Department).filter(Department.department_id == patient_in.depart).first()

        if not depart:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="입력된 부서가 존재하지 않습니다.",
            )

    if patient_in.admitted_ward:
        ward = db.query(Ward).filter(Ward.ward_id == patient_in.admitted_ward).first()

        if not ward:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="입력된 입원병동이 존재하지 않습니다.",
            )

    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이 환자 번호로 등록된 사용자가 이미 존재합니다.",
        )

    # Publish user.registered event to Kafka
    event = PatientRegisteredEvent(
        number = patient_in.number,
        name = patient_in.name,
        birth = patient_in.birth,
        gender = patient_in.gender,
        depart = patient_in.depart,
        admitted_ward = patient_in.admitted_ward,
        manage_practitioner = patient_in.manage_practitioner,
    )

    await publish_event(
        topic=settings.KAFKA_TOPIC_AUTH,
        event=event.model_dump(),
        key=patient_in.patient_number
    )

    return


@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
async def patient_login(
        *,
        db: AsyncSession = Depends(get_db),
        login_in: PatientLogin,
):
    patient = await crud_patient.get_by_patient_number(db, patient_number=login_in.patient_number)

    if not patient or not verify_password(login_in.patient_password, patient.patient_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="환자 번호 또는 생년월일이 올바르지 않습니다.",
        )

    patient_id = patient.patient_id

    data = {
        "PatientId" : str(patient_id)
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
    patient = await crud_patient.get(db, id=patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return PatientSchema(patient_id=patient.patient_id)


@router.post("/refresh", response_model=Token, status_code=status.HTTP_200_OK)
async def refresh_token(
        *,
        db: AsyncSession = Depends(get_db),
        user_id: str = Depends(get_current_patient_id),
        request: Request,
):
    """
    Refresh Token을 사용하여 새로운 Access/Refresh Token 발급
    """

    # 3. 사용자 존재 여부 및 활성화 상태 확인
    user = await crud_patient.get(db, id=user_id)
    if not user:
        status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if not user.is_active:
        status_code = status.HTTP_403_FORBIDDEN
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )


    data = {
        "PatientId" : user_id,
    }

    # 4. 새로운 토큰 쌍 발급
    return {
        "access_token": create_patient_access_token(data),
        "refresh_token": create_patient_refresh_token(data),
        "token_type": "bearer",
    }