import json
import logging
import faust
import time
from datetime import datetime, timezone

from common.schemas.events import BiosignalECGPPGEvent
from common.db.session import SessionLocal
from biosignal.app.models.biosignals import BPInitLog, BPMeasureLog
from consumer_analysis.app.main import app, biosignal_topic
from .bp_analysis import BpManager, BpFeatures
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

# PPG 분석 임계치: 500Hz * 30초 = 15,000 샘플
PPG_ANALYSIS_THRESHOLD = 500 * 30

# Dispatch table: event_type -> (pydantic model, analysis function)
_HANDLERS = {}
ECG_PPG_TO_BP = app.Table("ecg_ppg_to_bp", default=dict)


def _register(event_type: str, model_cls):
    def decorator(fn):
        _HANDLERS[event_type] = (model_cls, fn)
        return fn
    return decorator


@_register("biosignal.ECG_PPG.received", BiosignalECGPPGEvent)
async def analyze_ecg(event: BiosignalECGPPGEvent):
    logger.info(
        f"analyze_ecg, "
        f"ECG analysis - patient_id: {event.patient_id}, "
        f"ECG signal_length: {len(event.ecg)}, "
        f"PPG signal_length: {len(event.ppg)}, "
        f"timestamp: {event.timestamp}"
    )

    # TODO: Connect ML inference pipeline (arrhythmia detection, heart rate)


@app.agent(biosignal_topic)
async def process_biosignal(stream):
    async for raw in stream:
        try:
            payload = json.loads(raw.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to decode biosignal message: {e}")
            continue

        event_type = payload.get('event_type')
        if event_type != 'biosignal.ECG_PPG.received':
            logger.debug(f"Skipping non-ECG_PPG event: {event_type}")
            continue


        try:
            event = BiosignalECGPPGEvent(**payload)
        except Exception as e:
            logger.warning(f"Failed to parse BiosignalECGPPGEvent: {e}")
            continue

        patient_id = event.patient_id
        current_ecg = event.ecg
        current_ppg = event.ppg

        logger.info(
            f"Received signal for patient_id: {patient_id}, "
            f"ecg_signal_length: {len(current_ecg)}, "
            f"ppg_signal_length: {len(current_ppg) if current_ppg is not None else 0}"
        )
        now = time.time()

        # 1. 버퍼 가져오기 또는 초기화 (옛 스키마/부분 저장 방어)
        buffer = ECG_PPG_TO_BP.get(patient_id)
        if not isinstance(buffer, dict) or 'ecg' not in buffer or 'ppg' not in buffer:
            buffer = {
                'start_timestamp': event.timestamp,
                'received_at': now,
                'ecg': [],
                'ppg': [],
            }
            ECG_PPG_TO_BP[patient_id] = buffer
        else:
            if 'received_at' not in buffer:
                legacy_start_time = buffer.get('start_time', now)
                buffer['received_at'] = legacy_start_time / 1000 if legacy_start_time > 10_000_000_000 else legacy_start_time

            if 'start_timestamp' not in buffer:
                buffered_sample_count = len(buffer.get('ppg') or [])
                buffered_duration_ms = int(buffered_sample_count * 1000 / 500)
                buffer['start_timestamp'] = event.timestamp - buffered_duration_ms

            ECG_PPG_TO_BP[patient_id] = buffer

        # ppg 데이터에 None 데이터가 들어올 경우 버퍼 초기화
        if current_ppg is None:
            logger.info(f"PPG Signal is None. Reinitializing buffer for patient_id: {patient_id}")
            del ECG_PPG_TO_BP[patient_id]
            continue

        # 2. 신호 축적

        buffer['ecg'].extend(current_ecg)
        buffer['ppg'].extend(current_ppg)
        ECG_PPG_TO_BP[patient_id] = buffer

        # 3. 분석 조건 확인: PPG 샘플이 임계치(500Hz * 30s)에 도달했는지
        if len(buffer['ppg']) >= PPG_ANALYSIS_THRESHOLD:
            logger.info(
                f"PPG buffer reached analysis threshold for patient_id: {patient_id} "
                f"(ppg: {len(buffer['ppg'])}, ecg: {len(buffer['ecg'])}, "
                f"elapsed: {now - buffer['received_at']:.2f}s)"
            )

            await analyze_ecg_ppg_batch(
                patient_id=patient_id,
                ecg=list(buffer['ecg']),
                ppg=list(buffer['ppg']),
                start_time=buffer['start_timestamp'] / 1000,
                end_time=event.timestamp / 1000
            )

            # 분석 완료 후 버퍼 초기화 (메모리 누수 방지)
            del ECG_PPG_TO_BP[patient_id]


async def analyze_ecg_ppg_batch(patient_id: str, ecg: list, ppg: list, start_time: float, end_time: float):
    """축적된 ECG/PPG 배치에 대한 분석 진입점."""
    logger.info(
        f"analyze_ecg_ppg_batch - patient_id: {patient_id}, "
        f"ecg_length: {len(ecg)}, ppg_length: {len(ppg)}"
    )


    async with SessionLocal() as db:
        bp_init_result = await db.execute(
            select(BPInitLog)
            .where(BPInitLog.patient_id == patient_id)
            .order_by(BPInitLog.created_at.desc())
        )
        bp_init_log = bp_init_result.scalars().first()

        if bp_init_log is None:
            raise ValueError(f"No BPInitLog found for patient_id: {patient_id}")

        base_sbp = bp_init_log.baseSBP
        base_dbp = bp_init_log.baseDBP

        if base_dbp is None:
            base_dbp = 80

        if base_sbp is None:
            base_sbp = 120

        bp_features = BpFeatures(
            pttf=bp_init_log.pttf,
            pttd=bp_init_log.pttd,
            d_ptt=bp_init_log.dPtt,
            d_ptt_norm=bp_init_log.dPttNorm,
            up_slope=bp_init_log.upSlope,
            pw50=bp_init_log.pw50,
            dia_slope=bp_init_log.diaSlope,
            auc=bp_init_log.auc,
            acdc=bp_init_log.acdc,
            rr_mean=bp_init_log.rrMean,
            rr_std=bp_init_log.rrStd,
            corr_mean=0.0,
            keep_ratio=1.0,
        )

        bp_manager = BpManager('../statics/global_delta_sbp_resta_remove_keepratio.onnx',
                               '../statics/global_delta_dbp_resta_remove_keepratio.onnx', base_sbp, base_dbp, bp_features)
        signal_features = bp_manager.process_data(ecg, ppg)
        if signal_features is None:
            raise ValueError(f"Failed to extract BP features for patient_id: {patient_id}")

        predicted_sbp, predicted_dbp = bp_manager.predict_blood_pressure(signal_features)

        bp_measure_log = BPMeasureLog(patient_id=patient_id, base_sbp=base_sbp, base_dbp=base_dbp,
                                      predicted_sbp=base_sbp + predicted_sbp, predicted_dbp=base_dbp + predicted_dbp,
                                      started_at=datetime.fromtimestamp(start_time, tz=timezone.utc),
                                      ended_at=datetime.fromtimestamp(end_time, tz=timezone.utc))
        db.add(bp_measure_log)
        await db.commit()

    # TODO: ML 추론 파이프라인 연결 (BP 추정 등)
