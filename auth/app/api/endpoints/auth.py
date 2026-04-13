from fastapi import APIRouter, status, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request
from jose import jwt, JWTError
from datetime import datetime
from common.core.auth import get_current_user_id
from common.core.security import verify_password, create_access_token, create_refresh_token
from common.core.config import settings
from common.core.kafka_producer import publish_event
from common.db.session import get_db
from common.schemas.events import UserRegisteredEvent
from auth.app.schemas.auth import Register, Token, Login, RefreshToken
from auth.app.schemas.auth import User as UserSchema
from auth.app.api.commons.crud_user import user as crud_user

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
        *,
        db: AsyncSession = Depends(get_db),
        user_in: Register,
):
    """
    새로운 사용자 등록 (회원가입)
    User 생성 후 Kafka 이벤트를 발행하여 PatientProfile 생성을 트리거합니다.
    """
    user = await crud_user.get_by_username(db, username=user_in.username)

    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이 사용자명으로 등록된 사용자가 이미 존재합니다.",
        )

    new_user = await crud_user.create(db, obj_in=user_in)

    # Publish user.registered event to Kafka
    event = UserRegisteredEvent(
        user_id=str(new_user.user_id),
        username=new_user.username,
        timestamp=datetime.utcnow()
    )
    await publish_event(
        topic=settings.KAFKA_TOPIC_AUTH,
        event=event.model_dump(),
        key=str(new_user.user_id)
    )

    return


@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
async def login(
        *,
        db: AsyncSession = Depends(get_db),
        login_in: Login,
):
    """
    로그인 및 토큰 발급
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

    user_id = user.user_id

    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=Token, status_code=status.HTTP_200_OK)
async def refresh_token(
        *,
        db: AsyncSession = Depends(get_db),
        token_in: RefreshToken,
        request: Request
):
    """
    Refresh Token을 사용하여 새로운 Access/Refresh Token 발급
    """
    # 1. Refresh Token 디코드 및 검증
    try:
        payload = jwt.decode(
            token_in.refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 Refresh Token입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. 토큰 타입 확인
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰 타입입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 사용자 정보가 없습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

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

    # 4. 새로운 토큰 쌍 발급
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserSchema, status_code=status.HTTP_200_OK)
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

    return UserSchema(user_id=user.user_id)