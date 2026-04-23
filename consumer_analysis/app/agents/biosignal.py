import json
import logging

from common.schemas.events import BiosignalECGEvent, BiosignalPPGEvent, BiosignalRESPEvent
from consumer_analysis.app.main import app, biosignal_topic

logger = logging.getLogger(__name__)

# Dispatch table: event_type -> (pydantic model, analysis function)
_HANDLERS = {}


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
    """Faust agent that dispatches biosignal events to analysis handlers."""
    async for raw in stream:
        try:
            data = json.loads(raw)
            event_type = data.get("event_type")

            handler_entry = _HANDLERS.get(event_type)
            if handler_entry is None:
                logger.warning(f"No analysis handler for event_type: {event_type}")
                continue

            model_cls, handler_fn = handler_entry
            event = model_cls(**data)
            await handler_fn(event)

        except Exception as e:
            logger.error(f"Error processing biosignal event: {e}", exc_info=True)
