from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, status, Depends, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from biosignal.app.schemas.biosignal import ECGBiosignal, PPGBiosignal, RESPBiosignal, ECGAndPPGSignal, \
    BPAnalysisInitParams
from biosignal.app.schemas.biosignal import BioMatrics as BioMatricsRequest, BioMatricsAggregate, BioMetricAggregate, \
    BPMeasureAggregate
from common.core.config import settings
from common.core.auth import TokenPayload, get_current_patient_id, get_current_user_payload
from common.core.kafka_producer import publish_event
from common.db.session import get_db
from common.schemas.events import BiosignalECGEvent, BiosignalPPGEvent, BiosignalRESPEvent, BiosignalECGPPGEvent, \
    BiosignalBPInitEvent, BioMatrixEvent

router = APIRouter()

BIOMETRIC_COLUMNS = {"hr": "hr", "rr": "rr", "temp": "temp", "spo2": "spo2"}
ADMINISTRATOR_PERMISSION = "administrator"
PRACTITIONER_PERMISSION = "practitioner"


def get_biomatrix_time_range(start_time: int | None, end_time: int | None) -> tuple[datetime, datetime]:
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

    return start_dt, end_dt


async def read_single_biometric(
        *,
        patient_id: UUID,
        db: AsyncSession,
        metric_name: str,
        records_interval: int,
        start_time: int | None,
        end_time: int | None,
) -> list[BioMetricAggregate]:
    start_dt, end_dt = get_biomatrix_time_range(start_time, end_time)
    metric_column = BIOMETRIC_COLUMNS[metric_name]

    if records_interval == 0:
        query = text(f"""
            SELECT
                recorded_at,
                {metric_column} AS value
            FROM biosignal.bio_metrics
            WHERE patient_id = CAST(:patient_id AS uuid)
              AND recorded_at >= :start_dt
              AND recorded_at <= :end_dt
            ORDER BY recorded_at
        """)

        result = await db.execute(
            query,
            {
                "patient_id": str(patient_id),
                "start_dt": start_dt,
                "end_dt": end_dt,
            },
        )

        return [
            BioMetricAggregate(
                start_time=int(row["recorded_at"].timestamp() * 1000),
                end_time=int(row["recorded_at"].timestamp() * 1000),
                value=row["value"],
            )
            for row in result.mappings()
        ]

    bucket_seconds = records_interval * 60
    query = text(f"""
        SELECT
            FLOOR((EXTRACT(EPOCH FROM recorded_at) - :start_epoch) / :bucket_seconds)::bigint AS bucket_index,
            AVG({metric_column}) AS value
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
            "patient_id": str(patient_id),
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
            BioMetricAggregate(
                start_time=bucket_start,
                end_time=bucket_end,
                value=row["value"],
            )
        )

    return aggregates


async def ensure_practitioner_can_read_patient(
        *,
        db: AsyncSession,
        token_payload: TokenPayload,
        patient_id: UUID,
) -> None:
    user_result = await db.execute(
        text("""
            SELECT permissions, is_active
            FROM auth.users
            WHERE user_id = CAST(:user_id AS uuid)
            LIMIT 1
        """),
        {"user_id": token_payload.sub},
    )
    user = user_result.mappings().one_or_none()
    if user is None or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없거나 비활성화된 계정입니다.",
        )

    permission = user["permissions"]
    if permission == ADMINISTRATOR_PERMISSION:
        return

    if permission != PRACTITIONER_PERMISSION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="병원직 권한이 필요합니다.",
        )

    access_result = await db.execute(
        text("""
            SELECT 1
            FROM clinical_manage.patient_profile patient
            LEFT JOIN clinical_manage.practitioner_profiles practitioner
              ON practitioner.practitioner_id = CAST(:user_id AS uuid)
             AND practitioner.is_deleted IS FALSE
            WHERE patient.patient_id = CAST(:patient_id AS uuid)
              AND (
                patient.manage_practitioner_id = CAST(:user_id AS uuid)
                OR EXISTS (
                  SELECT 1
                  FROM clinical_manage.manage manage
                  WHERE manage.practitioner_id = CAST(:user_id AS uuid)
                    AND manage.patient_id = patient.patient_id
                )
                OR (
                  practitioner.department_id IS NOT NULL
                  AND practitioner.department_id = patient.department_id
                )
              )
            LIMIT 1
        """),
        {"user_id": token_payload.sub, "patient_id": str(patient_id)},
    )
    if access_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="해당 환자의 생체신호를 조회할 권한이 없습니다.",
        )

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

@router.get("/biomatrix/{patient_id}", response_model=list[BioMatricsAggregate], status_code=status.HTTP_200_OK)
async def read_biomatrix_aggregates(
        *,
        patient_id: UUID,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
        records_interval: int = Query(..., ge=0, description="Aggregation interval in minutes. 0이면 원본 데이터를 반환합니다."),
        start_time: int | None = Query(None, description="조회 시작 시간 timestamp ms"),
        end_time: int | None = Query(None, description="조회 종료 시간 timestamp ms"),
):
    await ensure_practitioner_can_read_patient(db=db, token_payload=token_payload, patient_id=patient_id)
    start_dt, end_dt = get_biomatrix_time_range(start_time, end_time)

    if records_interval == 0:
        query = text("""
            SELECT
                recorded_at,
                hr,
                rr,
                temp,
                spo2
            FROM biosignal.bio_metrics
            WHERE patient_id = CAST(:patient_id AS uuid)
              AND recorded_at >= :start_dt
              AND recorded_at <= :end_dt
            ORDER BY recorded_at
        """)

        result = await db.execute(
            query,
            {
                "patient_id": str(patient_id),
                "start_dt": start_dt,
                "end_dt": end_dt,
            },
        )

        return [
            BioMatricsAggregate(
                start_time=int(row["recorded_at"].timestamp() * 1000),
                end_time=int(row["recorded_at"].timestamp() * 1000),
                hr=row["hr"],
                rr=row["rr"],
                temp=row["temp"],
                spo2=row["spo2"],
            )
            for row in result.mappings()
        ]

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
            "patient_id": str(patient_id),
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


@router.get("/hr/{patient_id}", response_model=list[BioMetricAggregate], status_code=status.HTTP_200_OK)
async def read_hr_aggregates(
        *,
        patient_id: UUID,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
        records_interval: int = Query(..., ge=0, description="Aggregation interval in minutes. 0이면 원본 데이터를 반환합니다."),
        start_time: int | None = Query(None, description="조회 시작 시간 timestamp ms"),
        end_time: int | None = Query(None, description="조회 종료 시간 timestamp ms"),
):
    await ensure_practitioner_can_read_patient(db=db, token_payload=token_payload, patient_id=patient_id)
    return await read_single_biometric(
        patient_id=patient_id,
        db=db,
        metric_name="hr",
        records_interval=records_interval,
        start_time=start_time,
        end_time=end_time,
    )


@router.get("/rr/{patient_id}", response_model=list[BioMetricAggregate], status_code=status.HTTP_200_OK)
async def read_rr_aggregates(
        *,
        patient_id: UUID,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
        records_interval: int = Query(..., ge=0, description="Aggregation interval in minutes. 0이면 원본 데이터를 반환합니다."),
        start_time: int | None = Query(None, description="조회 시작 시간 timestamp ms"),
        end_time: int | None = Query(None, description="조회 종료 시간 timestamp ms"),
):
    await ensure_practitioner_can_read_patient(db=db, token_payload=token_payload, patient_id=patient_id)
    return await read_single_biometric(
        patient_id=patient_id,
        db=db,
        metric_name="rr",
        records_interval=records_interval,
        start_time=start_time,
        end_time=end_time,
    )


@router.get("/temp/{patient_id}", response_model=list[BioMetricAggregate], status_code=status.HTTP_200_OK)
async def read_temp_aggregates(
        *,
        patient_id: UUID,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
        records_interval: int = Query(..., ge=0, description="Aggregation interval in minutes. 0이면 원본 데이터를 반환합니다."),
        start_time: int | None = Query(None, description="조회 시작 시간 timestamp ms"),
        end_time: int | None = Query(None, description="조회 종료 시간 timestamp ms"),
):
    await ensure_practitioner_can_read_patient(db=db, token_payload=token_payload, patient_id=patient_id)
    return await read_single_biometric(
        patient_id=patient_id,
        db=db,
        metric_name="temp",
        records_interval=records_interval,
        start_time=start_time,
        end_time=end_time,
    )


@router.get("/spo2/{patient_id}", response_model=list[BioMetricAggregate], status_code=status.HTTP_200_OK)
async def read_spo2_aggregates(
        *,
        patient_id: UUID,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
        records_interval: int = Query(..., ge=0, description="Aggregation interval in minutes. 0이면 원본 데이터를 반환합니다."),
        start_time: int | None = Query(None, description="조회 시작 시간 timestamp ms"),
        end_time: int | None = Query(None, description="조회 종료 시간 timestamp ms"),
):
    await ensure_practitioner_can_read_patient(db=db, token_payload=token_payload, patient_id=patient_id)
    return await read_single_biometric(
        patient_id=patient_id,
        db=db,
        metric_name="spo2",
        records_interval=records_interval,
        start_time=start_time,
        end_time=end_time,
    )


@router.get("/bp/{patient_id}", response_model=list[BPMeasureAggregate], status_code=status.HTTP_200_OK)
async def read_bp_measures(
        *,
        patient_id: UUID,
        db: AsyncSession = Depends(get_db),
        token_payload: TokenPayload = Depends(get_current_user_payload),
        start_time: int | None = Query(None, description="조회 시작 시간 timestamp ms"),
        end_time: int | None = Query(None, description="조회 종료 시간 timestamp ms"),
):
    await ensure_practitioner_can_read_patient(db=db, token_payload=token_payload, patient_id=patient_id)
    start_dt, end_dt = get_biomatrix_time_range(start_time, end_time)
    query = text("""
        SELECT
            base_sbp,
            base_dbp,
            predicted_sbp,
            predicted_dbp,
            started_at,
            ended_at,
            created_at
        FROM biosignal.bp_measure_log
        WHERE patient_id = CAST(:patient_id AS uuid)
          AND ended_at >= :start_dt
          AND ended_at <= :end_dt
        ORDER BY ended_at
    """)
    result = await db.execute(
        query,
        {
            "patient_id": str(patient_id),
            "start_dt": start_dt,
            "end_dt": end_dt,
        },
    )

    return [
        BPMeasureAggregate(
            start_time=int(row["started_at"].timestamp() * 1000),
            end_time=int(row["ended_at"].timestamp() * 1000),
            recorded_at=int(row["created_at"].timestamp() * 1000),
            base_sbp=row["base_sbp"],
            base_dbp=row["base_dbp"],
            predicted_sbp=row["predicted_sbp"],
            predicted_dbp=row["predicted_dbp"],
        )
        for row in result.mappings()
    ]

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
