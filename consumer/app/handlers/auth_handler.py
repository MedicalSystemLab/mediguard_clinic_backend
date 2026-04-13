import logging
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from common.db.session import async_session_maker
from clinical_manage.app.models.info import PatientProfile

logger = logging.getLogger(__name__)


async def handle_user_registered(event_data: dict):
    """
    Handle user.registered event
    Creates a PatientProfile entry in clinical_manage schema

    Args:
        event_data: Event payload containing user_id, username, timestamp
    """
    try:
        user_id = event_data.get('user_id')
        username = event_data.get('username')
        timestamp = event_data.get('timestamp')

        logger.info(f"Processing user.registered event - user_id: {user_id}, username: {username}")

        # Create PatientProfile in clinical_manage database
        async with async_session_maker() as db:
            # Check if patient profile already exists
            result = await db.execute(
                select(PatientProfile).where(PatientProfile.patient_id == uuid.UUID(user_id))
            )
            existing_profile = result.scalars().first()

            if existing_profile:
                logger.warning(f"PatientProfile already exists for user_id: {user_id}")
                return

            # Create new PatientProfile
            # Note: These fields should be updated later by clinical staff
            patient_profile = PatientProfile(
                patient_id=uuid.UUID(user_id),
                patient_name="미입력",  # To be updated
                sex="U",  # Unknown, to be updated
                birth=datetime(1991, 1, 1).date(),  # Default, to be updated
                is_admitted=False,  # Default not admitted
                department_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # Placeholder
                admitted_ward_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # Placeholder
            )

            db.add(patient_profile)
            await db.commit()
            await db.refresh(patient_profile)

            logger.info(
                f"Successfully created PatientProfile for user_id: {user_id}, "
                f"patient_profile_id: {patient_profile.patient_profile_id}"
            )

    except Exception as e:
        logger.error(f"Failed to handle user.registered event: {e}", exc_info=True)
        raise  # Re-raise to prevent Kafka commit
