import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select
from common.db.session import SessionLocal
from common.core.security import compress_and_encrypt_data_list
from clinical_manage.app.models.info import PatientProfile, PractitionerProfiles, GenderEnum
from auth.app.models.auth import User, Patient
from biosignal.app.models.biosignals import Biosignals
from biosignal.app.models.biosignal_enum import BiosignalTypeEnum, MatricTypeEnum
from common.core.security import get_password_hash



from common.schemas.events import BiosignalECGEvent, BiosignalPPGEvent, BiosignalRESPEvent, BiosignalECGPPGEvent

logger = logging.getLogger(__name__)


async def handle_ecg_ppg_event(event_data: dict):
    logger.info(f"Biosignal event received: {event_data.get('event_type')}")
    event = BiosignalECGPPGEvent(**event_data)
    recorded_at_dt = datetime.fromtimestamp(event.timestamp / 1000, tz=timezone.utc)

    conpressed_and_encrypted_ecg_signal = compress_and_encrypt_data_list("h", event.ecg)
    conpressed_and_encrypted_ppg_signal = compress_and_encrypt_data_list("i", event.ppg)
    try:
        async with SessionLocal() as db:
            ecg_signal = Biosignals(patient_id=event.patient_id, biosignal_data=conpressed_and_encrypted_ecg_signal, biosignal_type='ECG', recorded_at=recorded_at_dt)
            ppg_signal = Biosignals(patient_id=event.patient_id, biosignal_data=conpressed_and_encrypted_ppg_signal, biosignal_type='PPG', recorded_at=recorded_at_dt)
            db.add(ecg_signal)
            db.add(ppg_signal)
            await db.commit()

    except Exception as e:
        logger.error(f"Failed to handle biosignal event: {e}", exc_info=True)
        raise

async def handle_ecg_event(event_data: dict):
    """
    Handle biosignal events (template for future implementation)

    Args:
        event_data: Event payload
    """
    event = BiosignalECGEvent(**event_data)
    recorded_at_dt = datetime.fromtimestamp(event.timestamp / 1000, tz=timezone.utc)

    compressed_and_encrypted_signal = compress_and_encrypt_data_list("h", event.signal)
    try:
        async with SessionLocal() as db:
            signal = Biosignals(patient_id=event.patient_id, biosignal_data=compressed_and_encrypted_signal, biosignal_type=event.signal_type, recorded_at=recorded_at_dt)
            db.add(signal)
            await db.commit()

    except Exception as e:
        logger.error(f"Failed to handle biosignal event: {e}", exc_info=True)
        raise



async def handle_ppg_event(event_data: dict):
    """
    Handle biosignal events (template for future implementation)

    Args:
        event_data: Event payload
    """
    event = BiosignalPPGEvent(**event_data)
    recorded_at_dt = datetime.fromtimestamp(event.timestamp / 1000, tz=timezone.utc)

    compressed_and_encrypted_signal = compress_and_encrypt_data_list("i", event.signal)
    try:
        async with SessionLocal() as db:
            signal = Biosignals(patient_id=event.patient_id, biosignal_data=compressed_and_encrypted_signal, biosignal_type=event.signal_type, recorded_at=recorded_at_dt)
            db.add(signal)
            await db.commit()

    except Exception as e:
        logger.error(f"Failed to handle biosignal event: {e}", exc_info=True)
        raise


async def handle_resp_event(event_data: dict):
    """
    Handle biosignal events (template for future implementation)

    Args:
        event_data: Event payload
    """
    event = BiosignalRESPEvent(**event_data)
    recorded_at_dt = datetime.fromtimestamp(event.timestamp / 1000, tz=timezone.utc)

    compressed_and_encrypted_signal = compress_and_encrypt_data_list("f", event.signal)
    try:
        async with SessionLocal() as db:
            signal = Biosignals(patient_id=event.patient_id, biosignal_data=compressed_and_encrypted_signal, biosignal_type=event.signal_type, recorded_at=recorded_at_dt)
            db.add(signal)
            await db.commit()

    except Exception as e:
        logger.error(f"Failed to handle biosignal event: {e}", exc_info=True)
        raise