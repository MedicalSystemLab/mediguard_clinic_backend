from typing import Optional
from fastapi import Header, HTTPException, status
from jose import jwt, JWTError
from common.core.config import settings
from pydantic import BaseModel

class TokenPayload(BaseModel):
    sub: Optional[str] = None
    iss: Optional[str] = None
    type: Optional[str] = None

async def get_current_user_id(
    authorization: str = Header(..., description="Bearer <token>")
) -> str:
    """
    API Gateway(Kong)에서 이미 서명 검증이 완료된 토큰을 파싱하여 user_id를 추출합니다.
    백엔드 부하를 줄이기 위해 서명 검증은 생략할 수 있지만, 
    보안상 필요하다면 여기서도 서명을 다시 검증할 수 있습니다.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )
    
    token = authorization.split(" ")[1]
    
    try:
        # Kong에서 검증을 마쳤으므로 여기서는 파싱만 수행 (부하 절감)
        # 만약 보안 강화를 원한다면 verify_signature=True로 설정
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM],
            options={"verify_signature": False} 
        )
        token_data = TokenPayload(**payload)

        if token_data.type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
            
        if token_data.sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject",
            )
            
        return token_data.sub
        
    except (JWTError, Exception) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
        )
