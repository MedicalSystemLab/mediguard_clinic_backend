from fastapi import APIRouter, status, Depends
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from auth.app.models.auth import User
from auth.app.schemas.auth import Patient
from common.db.session import get_db
from common.core.config import settings
from common.core.auth import get_current_patient_id
from common.core.kafka_producer import publish_event


router = APIRouter()
security = HTTPBearer()


@router.get("/profile", status_code=status.HTTP_200_OK)
async def get_profile(
    *,
    current_client_id: str = Depends(get_current_patient_id),
    db: AsyncSession = Depends(get_db)
):
    user = db.execute(select(User).where(User.client_id == current_client_id))
    user = user.scalar_one_or_none()

    if user:
        return {"client_id": current_client_id, "user": user}

    user = db.execute(select(Patient).where(Patient.patient_id == current_client_id))
    user = user.scalar_one_or_none()
    if user:
        return {"client_id": current_client_id, "user": user}

    return {"client_id": current_client_id}