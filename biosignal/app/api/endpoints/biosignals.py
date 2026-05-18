from fastapi import APIRouter, status, Depends

from biosignal.app.schemas.biosignal import ECGBiosignal, PPGBiosignal, RESPBiosignal, ECGAndPPGSignal, \
    BPAnalysisInitParams
from biosignal.app.schemas.biosignal import BioMatrics as BioMatricsRequest
from common.core.config import settings
from common.core.auth import get_current_patient_id
from common.core.kafka_producer import publish_event
from common.schemas.events import BiosignalECGEvent, BiosignalPPGEvent, BiosignalRESPEvent, BiosignalECGPPGEvent, \
    BiosignalBPInitEvent, BioMatrixEvent

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    return {"status": "ok"}

@router.post("/ecg_ppg", status_code=status.HTTP_200_OK)
async def collect_ecg_ppg_signal(
        *,
        patient_id: str = Depends(get_current_patient_id),
        signal_in: ECGAndPPGSignal
):
    event = BiosignalECGPPGEvent(
        patient_id=patient_id,
        ecg=signal_in.ecg,
        ppg=signal_in.ppg,
        timestamp=signal_in.recorded_at
    )

    await publish_event(
        topic=settings.KAFKA_TOPIC_BIOSIGNAL,
        event=event.model_dump(),
        key=patient_id
    )

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

@router.post("/biomatrix", status_code=status.HTTP_201_CREATED)
async def collect_biomatrix_signal(
        *,
        patient_id: str = Depends(get_current_patient_id),
        matrix_in: BioMatricsRequest
):

    event = BioMatrixEvent(
        patient_id=patient_id,
        hr=matrix_in.hr,
        rr=matrix_in.rr,
        spo2=matrix_in.spo2,
        temperature=matrix_in.temperature,
        recorded_at=matrix_in.recorded_at
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
        signal_in: PPGBiosignal
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
async def collect_resp_signal(
        *,
        patient_id: str = Depends(get_current_patient_id),
        signal_in: RESPBiosignal
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

@router.post("/bp/init", status_code=status.HTTP_201_CREATED)
async def init_bp_measurement(
        *,
        patient_id: str = Depends(get_current_patient_id),
        bp_init_in: BPAnalysisInitParams
):
    event = BiosignalBPInitEvent(
        patient_id=patient_id,
        **bp_init_in.model_dump(),
    )

    await publish_event(
        topic=settings.KAFKA_TOPIC_BIOSIGNAL,
        event=event.model_dump(),
        key=patient_id
    )