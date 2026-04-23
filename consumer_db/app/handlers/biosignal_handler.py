import logging
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from common.db.session import SessionLocal
from common.core.security import compress_and_encrypt_int_list, compress_and_encrypt_float_list
from clinical_manage.app.models.info import PatientProfile, PractitionerProfiles, GenderEnum
from auth.app.models.auth import User, Patient
from biosignal.app.models.biosignals import Biosignals
from common.core.security import get_password_hash



from common.schemas.events import BiosignalECGEvent, BiosignalPPGEvent, BiosignalRESPEvent

logger = logging.getLogger(__name__)


async def handle_ecg_event(event_data: dict):
    """
    Handle biosignal events (template for future implementation)

    Args:
        event_data: Event payload
    """
    logger.info(f"Biosignal event received: {event_data.get('event_type')}")
    event = BiosignalECGEvent(**event_data)
    compressed_and_encrypted_signal = compress_and_encrypt_int_list(event.signal)
    try:
        async with SessionLocal() as db:
            signal = Biosignals(patient_id=event.patient_id, biosignal_data=compressed_and_encrypted_signal, biosignal_type=event.signal_type, recorded_at=event.timestamp)
            db.add(signal)
            await db.commit()



    except Exception as e:
        logger.error(f"Failed to handle biosignal event: {e}", exc_info=True)
        raise



    # TODO: Implement biosignal event processing logic
    pass


async def handle_ppg_event(event_data: dict):
    """
    Handle biosignal events (template for future implementation)

    Args:
        event_data: Event payload
    """
    event = BiosignalPPGEvent(**event_data)
    logger.info(
        f"ECG analysis - patient_id: {event.patient_id}, "
        f"signal_length: {len(event.signal)}, "
        f"timestamp: {event.timestamp}"
    )
    logger.info(f"Biosignal event received: {event_data.get('event_type')}")
    # TODO: Implement biosignal event processing logic
    pass


async def handle_resp_event(event_data: dict):
    """
    Handle biosignal events (template for future implementation)

    Args:
        event_data: Event payload
    """
    event = BiosignalRESPEvent(**event_data)
    logger.info(
        f"ECG analysis - patient_id: {event.patient_id}, "
        f"signal_length: {len(event.signal)}, "
        f"timestamp: {event.timestamp}"
    )
    logger.info(f"Biosignal event received: {event_data.get('event_type')}")
    # TODO: Implement biosignal event processing logic
    pass
