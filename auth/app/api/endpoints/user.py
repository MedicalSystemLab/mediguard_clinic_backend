from fastapi import APIRouter, status, HTTPException, Depends, Request
from sqlalchemy import delete, false, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from uuid import UUID
from common.core.auth import TokenPayload, get_current_user_id, get_current_user_payload
from common.core.security import get_password_hash, verify_password, create_user_access_token, create_user_refresh_token
from common.core.config import settings
from common.core.kafka_producer import publish_event
from common.db.session import get_db
from common.schemas.events import UserRegisteredEvent
from auth.app.schemas.auth import (
    FCMDeviceRegister,
    FCMDeviceRegisterResponse,
    Token,
    UserLogin,
    UserLogout,
    UserLogoutResponse,
    UserMeResponse,
    UserPasswordReset,
    UserPasswordResetResponse,
    UserRegister,
)
from auth.app.schemas.auth import User as UserSchema
from auth.app.api.commons.crud_user import user as crud_user
from auth.app.models.auth import FCMToken

router = APIRouter()
security = HTTPBearer()

HOSPITAL_USER_PERMISSIONS = {"administrator", "practitioner"}


def ensure_hospital_user(token_payload: TokenPayload) -> None:
    if token_payload.permissions not in HOSPITAL_USER_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="병원직 사용자 권한이 필요합니다.",
        )


def ensure_access_token(token_payload: TokenPayload) -> None:
    if token_payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Token이 필요합니다.",
        )


def get_token_user_id(token_payload: TokenPayload) -> UUID:
    try:
        return UUID(token_payload.sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject가 올바르지 않습니다.",
        ) from exc

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
        *,
        db: AsyncSession = Depends(get_db),
        user_in: UserRegister,
):
    user = await crud_user.get_by_username(db, username=user_in.username)

    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이 사용자명으로 등록된 사용자가 이미 존재합니다.",
        )

    # Publish user.registered event to Kafka
    event = UserRegisteredEvent(
        username=user_in.username,
        password=user_in.password,
        practitioner_name=user_in.practitioner_name,
        rule=user_in.rule,
        department_id=user_in.department_id,
        ward_id=user_in.ward_id,
    )
    await publish_event(
        topic=settings.KAFKA_TOPIC_AUTH,
        event=event.model_dump(),
        key=user_in.username
    )

    return

@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
async def user_login(
        *,
        db: AsyncSession = Depends(get_db),
        login_in: UserLogin,
):
    """
    병원직, 관리자 로그인 및 토큰 발급
    """
    user = await crud_user.get_by_username(db, username=login_in.username)

    if not user or not verify_password(login_in.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자명 또는 비밀번호가 올바르지 않습니다.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다. 관리자에게 문의하세요.",
        )

    user_id = str(user.user_id)
    permission = user.permissions.value
    is_reset_password = user.is_reset_password

    data = {
        "userId" : user_id,
        "permissions" : permission
    }

    return {
        "access_token": create_user_access_token(data),
        "refresh_token": create_user_refresh_token(data),
        "token_type": "bearer",
        "is_reset_password": is_reset_password
    }


@router.post("/fcm", response_model=FCMDeviceRegisterResponse, status_code=status.HTTP_200_OK)
async def register_fcm_device(
        *,
        db: AsyncSession = Depends(get_db),
        device_in: FCMDeviceRegister,
        token_payload: TokenPayload = Depends(get_current_user_payload),
):
    """
    병원직/관리자 FCM 디바이스 등록
    """
    ensure_access_token(token_payload)
    ensure_hospital_user(token_payload)
    user_id = get_token_user_id(token_payload)

    try:
        result = await db.execute(select(FCMToken).where(FCMToken.user_id == user_id))
        fcm_token = result.scalar_one_or_none()

        if fcm_token:
            fcm_token.token = device_in.fcm_token
            fcm_token.platform = device_in.platform or fcm_token.platform
            fcm_token.updated_at = func.now()
        else:
            db.add(
                FCMToken(
                    user_id=user_id,
                    token=device_in.fcm_token,
                    platform=device_in.platform or "android",
                )
            )

        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="FCM 기기 등록에 실패했습니다.",
        ) from exc

    return FCMDeviceRegisterResponse(registered=True)


@router.post("/logout", response_model=UserLogoutResponse, status_code=status.HTTP_200_OK)
async def user_logout(
        *,
        db: AsyncSession = Depends(get_db),
        logout_in: UserLogout,
        token_payload: TokenPayload = Depends(get_current_user_payload),
):
    """
    병원직/관리자 로그아웃 및 FCM 디바이스 비활성화
    """
    ensure_access_token(token_payload)
    ensure_hospital_user(token_payload)
    user_id = get_token_user_id(token_payload)

    try:
        await db.execute(
            delete(FCMToken).where(
                FCMToken.user_id == user_id,
                FCMToken.token == logout_in.fcm_token,
            )
        )
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="로그아웃 처리에 실패했습니다.",
        ) from exc

    return UserLogoutResponse(logged_out=True)


@router.post("/refresh", response_model=Token, status_code=status.HTTP_200_OK)
async def refresh_token(
        *,
        db: AsyncSession = Depends(get_db),
        user_id: str = Depends(get_current_user_id),
        request: Request,
):
    """
    Refresh Token을 사용하여 새로운 Access/Refresh Token 발급
    """

    # 3. 사용자 존재 여부 및 활성화 상태 확인
    user = await crud_user.get(db, id=user_id)
    if not user:
        status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if not user.is_active:
        status_code = status.HTTP_403_FORBIDDEN
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )

    permission = user.permissions.value

    data = {
        "userId" : user_id,
        "permissions" : permission
    }

    # 4. 새로운 토큰 쌍 발급
    return {
        "access_token": create_user_access_token(data),
        "refresh_token": create_user_refresh_token(data),
        "token_type": "bearer",
    }


@router.post("/password-reset", response_model=UserPasswordResetResponse, status_code=status.HTTP_200_OK)
async def reset_user_password(
        *,
        db: AsyncSession = Depends(get_db),
        user_id: str = Depends(get_current_user_id),
        password_in: UserPasswordReset,
):
    """
    병원직/관리자 최초 또는 강제 비밀번호 재설정 처리
    """
    user = await crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )

    user.password_hash = get_password_hash(password_in.password)
    user.is_reset_password = False
    await db.commit()

    return UserPasswordResetResponse(is_reset_password=False)


@router.get("/me", response_model=UserMeResponse, status_code=status.HTTP_200_OK)
async def read_user_me(
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db)
):
    """
    현재 로그인된 사용자 정보 가져오기 (자동 로그인용)
    """
    user = await crud_user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return UserMeResponse(user_id=user.user_id, permissions=user.permissions.value)
