import json
import logging
import faust
import time

from common.schemas.events import BiosignalECGEvent, BiosignalPPGEvent, BiosignalRESPEvent
from consumer_analysis.app.main import app, biosignal_topic

logger = logging.getLogger(__name__)

# Dispatch table: event_type -> (pydantic model, analysis function)
_HANDLERS = {}
SIGNAL_BUFFER = app.Table("biosignal_buffer", default=dict)


def _register(event_type: str, model_cls):
    def decorator(fn):
        _HANDLERS[event_type] = (model_cls, fn)
        return fn
    return decorator


@_register("biosignal.ECG.received", BiosignalECGEvent)
async def analyze_ecg(event: BiosignalECGEvent):
    logger.info(
        f"ECG analysis - patient_id: {event.patient_id}, "
        f"signal_length: {len(event.signal)}, "
        f"timestamp: {event.timestamp}"
    )
    # TODO: Connect ML inference pipeline (arrhythmia detection, heart rate)


@_register("biosignal.PPG.received", BiosignalPPGEvent)
async def analyze_ppg(event: BiosignalPPGEvent):
    logger.info(
        f"PPG analysis - patient_id: {event.patient_id}, "
        f"signal_length: {len(event.signal)}, "
        f"timestamp: {event.timestamp}"
    )
    # TODO: Connect ML inference pipeline (SpO2 estimation, blood pressure)


@_register("biosignal.RESP.received", BiosignalRESPEvent)
async def analyze_resp(event: BiosignalRESPEvent):
    logger.info(
        f"RESP analysis - patient_id: {event.patient_id}, "
        f"signal_length: {len(event.signal)}, "
        f"timestamp: {event.timestamp}"
    )
    # TODO: Connect ML inference pipeline (respiratory rate calculation)


@app.agent(biosignal_topic)
async def process_biosignal(stream):
    async for event in stream:
        patient_id = event.patient_id
        current_signal = event.signal
        now = time.time()

        # 1. 버퍼 가져오기 또는 초기화
        buffer = SIGNAL_BUFFER[patient_id]
        if not buffer:
            buffer = {'start_time': now, 'signals': []}

        # 2. 신호 축적
        buffer['signals'].extend(current_signal)

        # 3. 분석 조건 확인 (최소 1분 경과 여부)
        elapsed_time = now - buffer['start_time']

        if elapsed_time >= 60:  # 60초 경과
            logger.info(f"Signal accumulation for {patient_id} reached 1 minute. buffer_size: {len(buffer['signals'])}")
            # # 4. 품질 검사 (첨도 계산)
            # kurt_val = kurtosis(buffer['signals'], fisher=True)
            #
            # if kurt_val > 5.0:  # 품질이 좋은 경우 (기준치 5.0은 조정 가능)
            #     logger.info(f"High quality signal (Kurt: {kurt_val:.2f}). Starting analysis for {patient_id}")
            #
            #     # 실제 분석 로직 실행
            #     await analyze_ecg_batch(patient_id, buffer['signals'])
            #
            #     # 분석 완료 후 데이터 삭제 (저장공간 누수 방지 핵심)
            #     del SIGNAL_BUFFER[patient_id]
            # else:
            #     # 품질이 좋지 않은 경우: del 하지 않음 -> 다음 루프에서 데이터가 계속 쌓임 (시간 연장)
            #     logger.warning(f"Low quality signal (Kurt: {kurt_val:.2f}). Extending accumulation for {patient_id}")
            #     SIGNAL_BUFFER[patient_id] = buffer  # 업데이트된 버퍼 저장
        else:
            # 1분이 안 되었으면 버퍼 업데이트만 수행
            SIGNAL_BUFFER[patient_id] = buffer


async def analyze_ecg_batch(patient_id, full_signals):
    # 여기서 실제 ML 추론이나 DB 저장을 수행합니다.
    logger.info(f"Processing {len(full_signals)} samples for {patient_id}")
    pass