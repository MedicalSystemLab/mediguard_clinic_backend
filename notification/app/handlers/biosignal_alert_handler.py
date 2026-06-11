import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text

from common.db.session import SessionLocal
from notification.app.services.fcm import FcmClient

logger = logging.getLogger(__name__)
fcm_client = FcmClient()


@dataclass(frozen=True)
class MetricValue:
    metric_type: str
    value: float


@dataclass(frozen=True)
class ThresholdViolation:
    metric_type: str
    measured_value: float
    threshold_min: float | None
    threshold_max: float | None
    direction: str


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_recorded_at(event_data: dict) -> datetime | None:
    timestamp = event_data.get("recorded_at") or event_data.get("ended_at")
    try:
        return datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _biomatrix_metrics(event_data: dict) -> list[MetricValue]:
    source_values = {
        "BPM": event_data.get("hr"),
        "RESP": event_data.get("rr"),
        "TEMP": event_data.get("temperature"),
        "SPO2": event_data.get("spo2"),
    }
    return [
        MetricValue(metric_type=metric_type, value=value)
        for metric_type, raw_value in source_values.items()
        if (value := _to_float(raw_value)) is not None
    ]


def _bp_metrics(event_data: dict) -> list[MetricValue]:
    source_values = {
        "BP_SYS": event_data.get("predicted_sbp"),
        "BP_DIA": event_data.get("predicted_dbp"),
    }
    return [
        MetricValue(metric_type=metric_type, value=value)
        for metric_type, raw_value in source_values.items()
        if (value := _to_float(raw_value)) is not None
    ]


def _find_violations(metrics: list[MetricValue], thresholds: dict[str, dict]) -> list[ThresholdViolation]:
    violations = []
    for metric in metrics:
        threshold = thresholds.get(metric.metric_type)
        if not threshold:
            continue

        min_value = threshold["min_value"]
        max_value = threshold["max_value"]
        if min_value is not None and metric.value < min_value:
            violations.append(
                ThresholdViolation(
                    metric_type=metric.metric_type,
                    measured_value=metric.value,
                    threshold_min=min_value,
                    threshold_max=max_value,
                    direction="LOW",
                )
            )
        elif max_value is not None and metric.value > max_value:
            violations.append(
                ThresholdViolation(
                    metric_type=metric.metric_type,
                    measured_value=metric.value,
                    threshold_min=min_value,
                    threshold_max=max_value,
                    direction="HIGH",
                )
            )
    return violations


async def _load_thresholds(db, patient_id: str) -> dict[str, dict]:
    result = await db.execute(
        text("""
            SELECT metric_type, min_value, max_value
            FROM biosignal.patient_threshold
            WHERE patient_id = CAST(:patient_id AS uuid)
              AND enabled IS TRUE
        """),
        {"patient_id": patient_id},
    )
    return {
        row["metric_type"]: {
            "min_value": row["min_value"],
            "max_value": row["max_value"],
        }
        for row in result.mappings()
    }


async def _load_recipients(db, patient_id: str) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT
                recipient.practitioner_id,
                fcm.token AS fcm_token
            FROM clinical_manage.patient_alert_recipient recipient
            JOIN auth.fcm_token fcm
              ON fcm.user_id = recipient.practitioner_id
            JOIN auth.users users
              ON users.user_id = recipient.practitioner_id
             AND users.is_active IS TRUE
            WHERE recipient.patient_id = CAST(:patient_id AS uuid)
              AND recipient.enabled IS TRUE
        """),
        {"patient_id": patient_id},
    )
    return [dict(row) for row in result.mappings()]


async def _write_alert_log(
        db,
        *,
        patient_id: str,
        practitioner_id: UUID | None,
        violation: ThresholdViolation,
        event_recorded_at: datetime | None,
        fcm_success: bool,
        error_message: str | None,
) -> None:
    await db.execute(
        text("""
            INSERT INTO biosignal.alert_log (
                patient_id,
                practitioner_id,
                metric_type,
                measured_value,
                threshold_min,
                threshold_max,
                direction,
                event_recorded_at,
                fcm_success,
                error_message
            )
            VALUES (
                CAST(:patient_id AS uuid),
                CAST(:practitioner_id AS uuid),
                :metric_type,
                :measured_value,
                :threshold_min,
                :threshold_max,
                :direction,
                :event_recorded_at,
                :fcm_success,
                :error_message
            )
        """),
        {
            "patient_id": patient_id,
            "practitioner_id": str(practitioner_id) if practitioner_id else None,
            "metric_type": violation.metric_type,
            "measured_value": violation.measured_value,
            "threshold_min": violation.threshold_min,
            "threshold_max": violation.threshold_max,
            "direction": violation.direction,
            "event_recorded_at": event_recorded_at,
            "fcm_success": fcm_success,
            "error_message": error_message[:1000] if error_message else None,
        },
    )


async def handle_biosignal_alert_event(event_data: dict) -> None:
    event_type = event_data.get("event_type")
    patient_id = event_data.get("patient_id")
    if not patient_id:
        return

    try:
        patient_id = str(UUID(patient_id))
    except (TypeError, ValueError):
        logger.warning("Skipping alert event with invalid patient_id: %s", patient_id)
        return

    if event_type == "biosignal.biomatrix.received":
        metrics = _biomatrix_metrics(event_data)
    elif event_type == "biosignal.BP.measured":
        metrics = _bp_metrics(event_data)
    else:
        return

    if not metrics:
        return

    event_recorded_at = _event_recorded_at(event_data)
    async with SessionLocal() as db:
        thresholds = await _load_thresholds(db, patient_id)
        violations = _find_violations(metrics, thresholds)
        if not violations:
            return

        recipients = await _load_recipients(db, patient_id)
        if not recipients:
            logger.info("No alert recipients for patient_id=%s", patient_id)
            for violation in violations:
                await _write_alert_log(
                    db,
                    patient_id=patient_id,
                    practitioner_id=None,
                    violation=violation,
                    event_recorded_at=event_recorded_at,
                    fcm_success=False,
                    error_message="No alert recipients",
                )
            await db.commit()
            return

        for violation in violations:
            title = "환자 생체신호 임계치 초과"
            body = f"{violation.metric_type} {violation.measured_value:g} ({violation.direction})"
            data = {
                "type": "biosignal.alert",
                "patient_id": patient_id,
                "metric_type": violation.metric_type,
                "measured_value": str(violation.measured_value),
                "direction": violation.direction,
            }
            for recipient in recipients:
                result = await fcm_client.send_alert(
                    token=recipient["fcm_token"],
                    title=title,
                    body=body,
                    data=data,
                )
                await _write_alert_log(
                    db,
                    patient_id=patient_id,
                    practitioner_id=recipient["practitioner_id"],
                    violation=violation,
                    event_recorded_at=event_recorded_at,
                    fcm_success=result.success,
                    error_message=result.error_message,
                )

        await db.commit()
