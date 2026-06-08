import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from aiokafka import AIOKafkaConsumer
from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from starlette.responses import StreamingResponse
from sqlalchemy import text

from common.core.auth import TokenPayload, decode_authorization_payload, decode_token_payload
from common.core.config import settings
from common.db.session import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter()

ADMINISTRATOR_PERMISSION = "administrator"
PRACTITIONER_PERMISSION = "practitioner"
BP_REALTIME_MAX_CLOCK_DIFF_MS = 20_000


@dataclass
class MonitoringSubscription:
    user_id: str
    permissions: str
    home_patient_ids: set[str] = field(default_factory=set)
    detail_patient_ids: set[str] = field(default_factory=set)


class MonitoringConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[WebSocket, MonitoringSubscription] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, token_data: TokenPayload) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[websocket] = MonitoringSubscription(
                user_id=token_data.sub,
                permissions=token_data.permissions or "",
            )

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(websocket, None)

    async def set_home_patients(self, websocket: WebSocket, patient_ids: set[str]) -> None:
        async with self._lock:
            subscription = self._connections.get(websocket)
            if subscription:
                subscription.home_patient_ids = patient_ids

    async def add_detail_patient(self, websocket: WebSocket, patient_id: str) -> None:
        async with self._lock:
            subscription = self._connections.get(websocket)
            if subscription:
                subscription.detail_patient_ids.add(patient_id)

    async def remove_detail_patient(self, websocket: WebSocket, patient_id: str) -> None:
        async with self._lock:
            subscription = self._connections.get(websocket)
            if subscription:
                subscription.detail_patient_ids.discard(patient_id)

    async def broadcast(self, patient_id: str, payload: dict, *, detail_only: bool = False) -> None:
        disconnected = []
        async with self._lock:
            recipients = []
            for websocket, subscription in self._connections.items():
                if patient_id in subscription.detail_patient_ids:
                    recipients.append(websocket)
                elif not detail_only and patient_id in subscription.home_patient_ids:
                    recipients.append(websocket)

        for websocket in recipients:
            try:
                await websocket.send_json(payload)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            await self.disconnect(websocket)


manager = MonitoringConnectionManager()
monitoring_consumer_task: asyncio.Task | None = None


class BPSseConnectionManager:
    def __init__(self) -> None:
        self._subscriptions: dict[asyncio.Queue, set[str]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, patient_id: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=20)
        async with self._lock:
            self._subscriptions[queue] = {patient_id}
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._subscriptions.pop(queue, None)

    async def broadcast(self, patient_id: str, payload: dict) -> None:
        async with self._lock:
            recipients = [
                queue
                for queue, patient_ids in self._subscriptions.items()
                if patient_id in patient_ids
            ]

        for queue in recipients:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Dropping BP SSE payload for patient_id: %s", patient_id)


bp_sse_manager = BPSseConnectionManager()


def get_token_from_websocket(websocket: WebSocket) -> TokenPayload:
    token = websocket.query_params.get("token")
    if token:
        return decode_token_payload(token)

    authorization = websocket.headers.get("authorization")
    if authorization:
        return decode_authorization_payload(authorization)

    raise ValueError("Missing token")


def get_token_from_sse_request(authorization: str | None) -> TokenPayload:
    if authorization:
        return decode_authorization_payload(authorization)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing token",
    )


async def can_access_patient(token_data: TokenPayload, patient_id: UUID) -> bool:
    if token_data.permissions == ADMINISTRATOR_PERMISSION:
        return True

    async with SessionLocal() as db:
        result = await db.execute(
            text("""
                SELECT 1
                FROM clinical_manage.patient_profile patient
                LEFT JOIN clinical_manage.practitioner_profiles practitioner
                  ON practitioner.practitioner_id = CAST(:user_id AS uuid)
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
            {"user_id": token_data.sub, "patient_id": str(patient_id)},
        )
        return result.scalar_one_or_none() is not None


async def send_error(websocket: WebSocket, message: str) -> None:
    await websocket.send_json({"type": "error", "message": message})


def format_sse_event(event_name: str, payload: dict) -> str:
    event_id = payload.get("timestamp") or payload.get("ended_at")
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_name}")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}")
    return "\n".join(lines) + "\n\n"


@router.get("/bp/{patient_id}/sse")
async def bp_measure_sse(
        *,
        patient_id: UUID,
        request: Request,
        authorization: str | None = Header(None, description="Bearer <token>"),
):
    token_data = get_token_from_sse_request(authorization)
    patient_id_str = str(patient_id)

    if token_data.permissions == "patient":
        if token_data.sub != patient_id_str:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="해당 환자의 혈압 측정 결과를 구독할 권한이 없습니다.",
            )
    elif token_data.permissions in {PRACTITIONER_PERMISSION, ADMINISTRATOR_PERMISSION}:
        if not await can_access_patient(token_data, patient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="해당 환자의 혈압 측정 결과를 구독할 권한이 없습니다.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="혈압 측정 결과를 구독할 권한이 없습니다.",
        )

    queue = await bp_sse_manager.subscribe(patient_id_str)

    async def event_generator():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break

                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                yield format_sse_event("bp.updated", payload)
        finally:
            await bp_sse_manager.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws/monitoring")
async def monitoring_websocket(websocket: WebSocket):
    try:
        token_data = get_token_from_websocket(websocket)
        if token_data.permissions not in {
            PRACTITIONER_PERMISSION,
            ADMINISTRATOR_PERMISSION,
        }:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, token_data)
    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")

            if action == "home.subscribe":
                requested_patient_ids = message.get("patient_ids")
                if not isinstance(requested_patient_ids, list):
                    await send_error(websocket, "patient_ids must be a list")
                    continue

                try:
                    patient_ids = {str(UUID(patient_id)) for patient_id in requested_patient_ids}
                except (TypeError, ValueError):
                    await send_error(websocket, "Invalid patient_id in patient_ids")
                    continue

                await manager.set_home_patients(websocket, patient_ids)
                await websocket.send_json({
                    "type": "home.subscribed",
                    "patient_ids": list(patient_ids),
                })
                continue

            if action == "detail.subscribe":
                patient_id = message.get("patient_id")
                try:
                    patient_uuid = UUID(patient_id)
                except (TypeError, ValueError):
                    await send_error(websocket, "Invalid patient_id")
                    continue

                if not await can_access_patient(token_data, patient_uuid):
                    await send_error(websocket, "Forbidden patient subscription")
                    continue

                await manager.add_detail_patient(websocket, str(patient_uuid))
                await websocket.send_json({
                    "type": "detail.subscribed",
                    "patient_id": str(patient_uuid),
                })
                continue

            if action == "detail.unsubscribe":
                patient_id = message.get("patient_id")
                try:
                    patient_uuid = UUID(patient_id)
                except (TypeError, ValueError):
                    await send_error(websocket, "Invalid patient_id")
                    continue

                await manager.remove_detail_patient(websocket, str(patient_uuid))
                await websocket.send_json({
                    "type": "detail.unsubscribed",
                    "patient_id": str(patient_uuid),
                })
                continue

            await send_error(websocket, "Unknown action")
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)


def build_realtime_payloads(event_data: dict) -> list[tuple[str, dict, bool]]:
    event_type = event_data.get("event_type")
    patient_id = event_data.get("patient_id")
    if not patient_id:
        return []

    if event_type == "biosignal.biomatrix.received":
        payload = {
            "type": "biomatrix.updated",
            "patient_id": patient_id,
            "timestamp": event_data.get("recorded_at"),
            "hr": event_data.get("hr"),
            "rr": event_data.get("rr"),
            "temp": event_data.get("temperature"),
            "spo2": event_data.get("spo2"),
        }
        return [(patient_id, payload, False)]

    if event_type == "biosignal.BP.measured":
        ended_at = event_data.get("ended_at")
        try:
            ended_at_ms = int(ended_at)
        except (TypeError, ValueError):
            logger.warning("Skipping BP measured event with invalid ended_at: %s", ended_at)
            return []

        current_time_ms = int(time.time() * 1000)
        if abs(current_time_ms - ended_at_ms) >= BP_REALTIME_MAX_CLOCK_DIFF_MS:
            return []

        payload = {
            "type": "bp.updated",
            "patient_id": patient_id,
            "timestamp": event_data.get("recorded_at"),
            "base_sbp": event_data.get("base_sbp"),
            "base_dbp": event_data.get("base_dbp"),
            "predicted_sbp": event_data.get("predicted_sbp"),
            "predicted_dbp": event_data.get("predicted_dbp"),
            "started_at": event_data.get("started_at"),
            "ended_at": ended_at,
        }
        return [(patient_id, payload, False)]

    if event_type == "biosignal.ECG_PPG.received":
        payloads = [
            (
                patient_id,
                {
                    "type": "signal.chunk",
                    "patient_id": patient_id,
                    "timestamp": event_data.get("timestamp"),
                    "signal_type": "ECG",
                    "signal": event_data.get("ecg"),
                },
                True,
            )
        ]
        if event_data.get("ppg") is not None:
            payloads.append(
                (
                    patient_id,
                    {
                        "type": "signal.chunk",
                        "patient_id": patient_id,
                        "timestamp": event_data.get("timestamp"),
                        "signal_type": "PPG",
                        "signal": event_data.get("ppg"),
                    },
                    True,
                )
            )
        return payloads

    signal_types = {
        "biosignal.ECG.received": "ECG",
        "biosignal.PPG.received": "PPG",
        "biosignal.RESP.received": "RESP",
    }
    signal_type = signal_types.get(event_type)
    if signal_type:
        payload = {
            "type": "signal.chunk",
            "patient_id": patient_id,
            "timestamp": event_data.get("timestamp"),
            "signal_type": signal_type,
            "signal": event_data.get("signal"),
        }
        return [(patient_id, payload, True)]

    return []


async def run_monitoring_consumer() -> None:
    while True:
        consumer = AIOKafkaConsumer(
            settings.KAFKA_TOPIC_BIOSIGNAL,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=f"mediguard-monitoring-ws-{uuid4()}",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        started = False
        try:
            await consumer.start()
            started = True
            async for message in consumer:
                for patient_id, payload, detail_only in build_realtime_payloads(message.value):
                    await manager.broadcast(patient_id, payload, detail_only=detail_only)
                    if payload.get("type") == "bp.updated":
                        await bp_sse_manager.broadcast(patient_id, payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Monitoring Kafka consumer failed, retrying: {e}", exc_info=True)
            await asyncio.sleep(5)
        finally:
            if started:
                await consumer.stop()


async def start_monitoring_consumer() -> None:
    global monitoring_consumer_task
    if monitoring_consumer_task is None or monitoring_consumer_task.done():
        monitoring_consumer_task = asyncio.create_task(run_monitoring_consumer())


async def stop_monitoring_consumer() -> None:
    global monitoring_consumer_task
    if monitoring_consumer_task is not None:
        monitoring_consumer_task.cancel()
        try:
            await monitoring_consumer_task
        except asyncio.CancelledError:
            pass
        monitoring_consumer_task = None
