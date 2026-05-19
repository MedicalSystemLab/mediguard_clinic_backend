from fastapi import APIRouter, status, Depends
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from auth.app.models.auth import User
from auth.app.models.auth import Patient
from clinical_manage.app.models.info import PatientProfile, PractitionerProfiles
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