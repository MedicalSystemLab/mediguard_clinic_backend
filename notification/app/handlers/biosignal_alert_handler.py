import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from auth.app.models.auth import FCMToken, User
from common.db.session import SessionLocal
from clinical_manage.app.models.info import Department, PatientProfile, PractitionerProfiles, Ward
from clinical_manage.app.models.manage import AlertConfig, PatientAlertRecipient
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


def _is_paused(paused_until: datetime | None, now: datetime) -> bool:
    if paused_until is None:
        return False
    if paused_until.tzinfo is None:
        paused_until = paused_until.replace(tzinfo=timezone.utc)
    return paused_until > now


async def _load_thresholds(db, patient_id: str) -> dict[str, dict]:
    result = await db.execute(
        select(AlertConfig).where(AlertConfig.patient_id == UUID(patient_id))
    )
    alert_config = result.scalar_one_or_none()
    if alert_config is None:
        alert_config = AlertConfig(patient_id=UUID(patient_id))
        db.add(alert_config)
        await db.flush()
        await db.refresh(alert_config)

    now = datetime.now(timezone.utc)
    thresholds = {}
    if not _is_paused(alert_config.bpm_alert_paused_until, now):
        thresholds["BPM"] = {"min_value": alert_config.bpm_min, "max_value": alert_config.bpm_max}
    if not _is_paused(alert_config.rr_alert_paused_until, now):
        thresholds["RESP"] = {"min_value": alert_config.rr_min, "max_value": alert_config.rr_max}
    if not _is_paused(alert_config.temp_alert_paused_until, now):
        thresholds["TEMP"] = {"min_value": alert_config.temp_min, "max_value": alert_config.temp_max}
    if not _is_paused(alert_config.spo2_alert_paused_until, now):
        thresholds["SPO2"] = {"min_value": alert_config.spo2_min, "max_value": alert_config.spo2_max}
    if not _is_paused(alert_config.bp_alert_paused_until, now):
        thresholds["BP_SYS"] = {"min_value": None, "max_value": alert_config.bp_max}
        thresholds["BP_DIA"] = {"min_value": alert_config.bp_min, "max_value": None}

    return thresholds


def _alert_body(violation: ThresholdViolation) -> str:
    direction = "낮음" if violation.direction == "LOW" else "높음"
    limit = violation.threshold_min if violation.direction == "LOW" else violation.threshold_max
    return f"{violation.metric_type} {violation.measured_value:g} ({direction}, 기준 {limit:g})"


def _alert_data(patient_id: str, violation: ThresholdViolation) -> dict[str, str]:
    return {
        "type": "biosignal.alert",
        "patient_id": patient_id,
        "metric_type": violation.metric_type,
        "measured_value": str(violation.measured_value),
        "threshold_min": "" if violation.threshold_min is None else str(violation.threshold_min),
        "threshold_max": "" if violation.threshold_max is None else str(violation.threshold_max),
        "direction": violation.direction,
    }


async def _load_recipients(db, patient_id: str) -> list[dict]:
    result = await db.execute(
        select(
            PatientAlertRecipient.practitioner_id,
            FCMToken.token.label("fcm_token"),
        )
        .join(FCMToken, FCMToken.user_id == PatientAlertRecipient.practitioner_id)
        .join(User, User.user_id == PatientAlertRecipient.practitioner_id)
        .where(
            PatientAlertRecipient.patient_id == UUID(patient_id),
            PatientAlertRecipient.enabled.is_(True),
            User.is_active.is_(True),
        )
    )
    return [dict(row) for row in result.mappings()]


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

    async with SessionLocal() as db:
        thresholds = await _load_thresholds(db, patient_id)
        violations = _find_violations(metrics, thresholds)
        if not violations:
            await db.commit()
            return

        recipients = await _load_recipients(db, patient_id)
        if not recipients:
            logger.info("No alert recipients for patient_id=%s", patient_id)
            await db.commit()
            return

        for violation in violations:
            title = "환자 생체신호 임계치 초과"
            body = _alert_body(violation)
            data = _alert_data(patient_id, violation)
            for recipient in recipients:
                result = await fcm_client.send_alert(
                    token=recipient["fcm_token"],
                    title=title,
                    body=body,
                    data=data,
                )
                if not result.success:
                    logger.warning(
                        "Failed to send FCM alert patient_id=%s practitioner_id=%s metric_type=%s error=%s",
                        patient_id,
                        recipient["practitioner_id"],
                        violation.metric_type,
                        result.error_message,
                    )

        await db.commit()
