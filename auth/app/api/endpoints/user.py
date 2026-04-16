from fastapi import APIRouter, status, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from common.core.auth import get_current_user_id
from common.core.security import verify_password, create_user_access_token, create_user_refresh_token
from common.core.config import settings
from common.core.kafka_producer import publish_event
from common.db.session import get_db
from common.schemas.events import UserRegisteredEvent
from auth.app.schemas.auth import UserRegister, Token, UserLogin, UserMeResponse
from auth.app.schemas.auth import User as UserSchema
from auth.app.api.commons.crud_user import user as crud_user

router = APIRouter()
security = HTTPBearer()

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

    data = {
        "userId" : user_id,
        "permissions" : permission
    }

    return {
        "access_token": create_user_access_token(data),
        "refresh_token": create_user_refresh_token(data),
        "token_type": "bearer",
    }


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