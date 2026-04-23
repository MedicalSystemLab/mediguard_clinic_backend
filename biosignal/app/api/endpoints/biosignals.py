from fastapi import APIRouter, status, Depends

from biosignal.app.schemas.biosignal import ECGBiosignal
from common.core.config import settings
from common.core.auth import get_current_patient_id
from common.core.kafka_producer import publish_event
from common.schemas.events import BiosignalECGEvent, BiosignalPPGEvent, BiosignalRESPEvent

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "ok"}

@router.post("/ecg", status_code=status.HTTP_200_OK)
async def collect_ecg_signal(
        *,
        patient_id: str = Depends(get_current_patient_id),
        signal_in: ECGBiosignal
):
    event = BiosignalECGEvent(
        patient_id=patient_id,
        signal_type="ECG",
        signal=signal_in.signal,
        timestamp=signal_in.recorded_at
    )

    await publish_event(
        topic=settings.KAFKA_TOPIC_BIOSIGNAL,
        event=event.model_dump(),
        key=patient_id
    )

    return

@router.post("/ppg", status_code=status.HTTP_200_OK)
async def collect_ppg_signal(
        *,
        patient_id: str = Depends(get_current_patient_id),
        signal_in: ECGBiosignal
):
    event = BiosignalPPGEvent(
        patient_id=patient_id,
        signal_type="PPG",
        signal=signal_in.signal,
        timestamp=signal_in.recorded_at
    )

    await publish_event(
        topic=settings.KAFKA_TOPIC_BIOSIGNAL,
        event=event.model_dump(),
        key=patient_id
    )

    return

@router.post("/resp", status_code=status.HTTP_200_OK)
async def collect_ecg_signal(
        *,
        patient_id: str = Depends(get_current_patient_id),
        signal_in: ECGBiosignal
):
    event = BiosignalRESPEvent(
        patient_id=patient_id,
        signal_type="RESP",
        signal=signal_in.signal,
        timestamp=signal_in.recorded_at
    )

    await publish_event(
        topic=settings.KAFKA_TOPIC_BIOSIGNAL,
        event=event.model_dump(),
        key=patient_id
    )

    return


@router.post("/ppg")
def collect_ppg_signal():
    pass


@router.post("/resp")
def collect_resp_signal():
    pass