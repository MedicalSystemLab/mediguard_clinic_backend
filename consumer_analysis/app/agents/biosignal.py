import json
import logging
import faust
import time

from common.schemas.events import BiosignalECGPPGEvent
from consumer_analysis.app.main import app, biosignal_topic

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
            buffer = {'start_time': now, 'ecg': [], 'ppg': []}
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
                f"elapsed: {now - buffer['start_time']:.2f}s)"
            )

            await analyze_ecg_ppg_batch(
                patient_id=patient_id,
                ecg=list(buffer['ecg']),
                ppg=list(buffer['ppg']),
            )

            # 분석 완료 후 버퍼 초기화 (메모리 누수 방지)
            del ECG_PPG_TO_BP[patient_id]


async def analyze_ecg_ppg_batch(patient_id: str, ecg: list, ppg: list):
    """축적된 ECG/PPG 배치에 대한 분석 진입점."""
    logger.info(
        f"analyze_ecg_ppg_batch - patient_id: {patient_id}, "
        f"ecg_length: {len(ecg)}, ppg_length: {len(ppg)}"
    )
    # TODO: ML 추론 파이프라인 연결 (BP 추정 등)