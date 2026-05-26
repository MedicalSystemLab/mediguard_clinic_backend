from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, status, Depends, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from biosignal.app.schemas.biosignal import ECGBiosignal, PPGBiosignal, RESPBiosignal, ECGAndPPGSignal, \
    BPAnalysisInitParams
from biosignal.app.schemas.biosignal import BioMatrics as BioMatricsRequest, BioMatricsAggregate
from common.core.config import settings
from common.core.auth import get_current_patient_id
from common.core.kafka_producer import publish_event
from common.db.session import get_db
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

@router.get("/biomatrix", response_model=list[BioMatricsAggregate], status_code=status.HTTP_200_OK)
async def read_biomatrix_aggregates(
        *,
        patient_id: str = Depends(get_current_patient_id),
        db: AsyncSession = Depends(get_db),
        records_interval: int = Query(..., gt=0, description="Aggregation interval in minutes"),
        start_time: int | None = Query(None, description="조회 시작 시간 timestamp ms"),
        end_time: int | None = Query(None, description="조회 종료 시간 timestamp ms"),
):
    if start_time is None and end_time is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time만 입력할 수 없습니다. start_time을 함께 입력하세요.",
        )

    now = datetime.now(timezone.utc)
    if start_time is None and end_time is None:
        end_dt = now
        start_dt = end_dt - timedelta(hours=24)
    else:
        start_dt = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc) if end_time is not None else now

    if start_dt >= end_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_time은 end_time보다 이전이어야 합니다.",
        )

    bucket_seconds = records_interval * 60
    query = text("""
        SELECT
            FLOOR((EXTRACT(EPOCH FROM recorded_at) - :start_epoch) / :bucket_seconds)::bigint AS bucket_index,
            AVG(hr) AS hr,
            AVG(rr) AS rr,
            AVG(temp) AS temp,
            AVG(spo2) AS spo2
        FROM biosignal.bio_metrics
        WHERE patient_id = CAST(:patient_id AS uuid)
          AND recorded_at >= :start_dt
          AND recorded_at <= :end_dt
        GROUP BY bucket_index
        ORDER BY bucket_index
    """)

    result = await db.execute(
        query,
        {
            "patient_id": patient_id,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "start_epoch": start_dt.timestamp(),
            "bucket_seconds": bucket_seconds,
        },
    )

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    interval_ms = records_interval * 60 * 1000

    aggregates = []
    for row in result.mappings():
        bucket_start = start_ms + int(row["bucket_index"]) * interval_ms
        bucket_end = min(bucket_start + interval_ms, end_ms)
        aggregates.append(
            BioMatricsAggregate(
                start_time=bucket_start,
                end_time=bucket_end,
                hr=row["hr"],
                rr=row["rr"],
                temp=row["temp"],
                spo2=row["spo2"],
            )
        )

    return aggregates

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
