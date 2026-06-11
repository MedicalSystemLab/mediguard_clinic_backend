from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from common.core.auth import TokenPayload, get_current_user_payload
from common.db.session import SessionLocal

router = APIRouter(prefix="/devices")

HOSPITAL_USER_PERMISSIONS = {"administrator", "practitioner"}


class DeviceRegisterRequest(BaseModel):
    fcm_token: str = Field(min_length=1, alias="fcmToken")
    platform: str | None = None


class DeviceRegisterResponse(BaseModel):
    registered: bool


def ensure_hospital_user(token_payload: TokenPayload) -> None:
    if token_payload.permissions not in HOSPITAL_USER_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="병원직 사용자 권한이 필요합니다.",
        )


@router.post("/register", response_model=DeviceRegisterResponse, status_code=status.HTTP_200_OK)
async def register_device(
        *,
        device_in: DeviceRegisterRequest,
        token_payload: TokenPayload = Depends(get_current_user_payload),
):
    ensure_hospital_user(token_payload)
    try:
        async with SessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO clinical_manage.practitioner_device (
                        practitioner_id,
                        fcm_token,
                        platform,
                        is_active,
                        last_seen_at,
                        updated_at
                    )
                    VALUES (
                        CAST(:practitioner_id AS uuid),
                        :fcm_token,
                        :platform,
                        true,
                        now(),
                        now()
                    )
                    ON CONFLICT (fcm_token)
                    DO UPDATE SET
                        practitioner_id = EXCLUDED.practitioner_id,
                        platform = EXCLUDED.platform,
                        is_active = true,
                        last_seen_at = now(),
                        updated_at = now()
                """),
                {
                    "practitioner_id": token_payload.sub,
                    "fcm_token": device_in.fcm_token,
                    "platform": device_in.platform,
                },
            )
            await db.commit()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="FCM 기기 등록에 실패했습니다.",
        ) from exc

    return DeviceRegisterResponse(registered=True)


@router.delete("/{fcm_token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(
        *,
        fcm_token: str,
        token_payload: TokenPayload = Depends(get_current_user_payload),
):
    ensure_hospital_user(token_payload)
    async with SessionLocal() as db:
        await db.execute(
            text("""
                UPDATE clinical_manage.practitioner_device
                SET is_active = false,
                    updated_at = now()
                WHERE practitioner_id = CAST(:practitioner_id AS uuid)
                  AND fcm_token = :fcm_token
            """),
            {
                "practitioner_id": token_payload.sub,
                "fcm_token": fcm_token,
            },
        )
        await db.commit()
