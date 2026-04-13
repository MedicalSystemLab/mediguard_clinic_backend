import logging
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from common.db.session import SessionLocal
from clinical_manage.app.models.info import PatientProfile
from auth.app.models.auth import User, Patient
from common.core.security import get_password_hash


logger = logging.getLogger(__name__)


async def handle_user_registered(event_data: dict):
    try:
        username = event_data.get('username')
        password = event_data.get('password')

        async with SessionLocal() as db:
            result = await db.execute(select(User).where(User.username == username))
            existing_user = result.scalars().first()

            if existing_user:
                logger.warning(f"User already exists: {username}")
                return

            user = User(username=username, password_hash=get_password_hash(password), is_active=True)
            db.add(user)
            await db.commit()
            await db.refresh(user)

    except Exception as e:
        logger.error(f"Failed to handle user.registered event: {e}", exc_info=True)
        raise

async def handle_patient_registered(event_data: dict):
    try:
        patient_number = event_data.get('patient_number')
        patient_name = event_data.get('patient_name')
        patient_password = event_data.get('patient_password')
        patient_sex = event_data.get('patient_sex')

        async with SessionLocal() as db:
            # Check if patient profile already exists


            # Create new PatientProfile
            # Note: These fields should be updated later by clinical staff
            patient_profile = Patient(
                patient_number=patient_number,
                patient_password=get_password_hash(patient_password),
            )

            db.add(patient_profile)
            await db.commit()
            await db.refresh(patient_profile)

    except Exception as e:
        logger.error(f"Failed to handle user.registered event: {e}", exc_info=True)
        raise  # Re-raise to prevent Kafka commit
