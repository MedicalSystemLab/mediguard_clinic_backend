import logging
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from common.db.session import SessionLocal
from clinical_manage.app.models.info import PatientProfile, PractitionerProfiles, GenderEnum
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
            await db.flush()

            profile = PractitionerProfiles(practitioner_id=user.user_id)
            db.add(profile)
            await db.commit()

    except Exception as e:
        logger.error(f"Failed to handle user.registered event: {e}", exc_info=True)
        raise

async def handle_patient_registered(event_data: dict):
    number = event_data.get('number')
    name = event_data.get('name')
    gender = event_data.get('gender')
    birth = event_data.get('birth')
    department = event_data.get('depart')
    ward = event_data.get('admitted_ward')
    manage_practitioner = event_data.get('manage_practitioner')

    try:


        async with SessionLocal() as db:
            try:
                patient_account = Patient(
                    patient_number=number,
                    patient_password=get_password_hash(birth),
                )
                db.add(patient_account)
                await db.flush()

                patient_profile = PatientProfile(
                    patient_id=patient_account.patient_id,
                    patient_name=name,
                    gender=gender,
                    birth=birth,
                    department_id=department,
                    admitted_ward_id=ward,
                    manage_practitioner_id=manage_practitioner,
                )
                db.add(patient_profile)
                await db.commit()


            except SQLAlchemyError as e:
                await db.rollback()
                logger.error(f"Failed to create patient profile: {e}")
                raise

    except Exception as e:
        logger.error(f"Failed to handle user.registered event: {e}", exc_info=True)
        raise  # Re-raise to prevent Kafka commit
