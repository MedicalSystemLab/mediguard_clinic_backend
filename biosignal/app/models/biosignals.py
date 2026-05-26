import uuid, uuid6
import enum
from sqlalchemy import String, UUID, TIMESTAMP, Enum, LargeBinary, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from biosignal.app.models.base import BiosignalBase
from biosignal.app.models.biosignal_enum import BiosignalTypeEnum, MatricTypeEnum


class Biosignals(BiosignalBase):
    __tablename__ = "biosignals"
    __table_args__ = {"schema": "biosignal"}

    biosignal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    biosignal_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    biosignal_type: Mapped[Enum] = mapped_column(Enum(BiosignalTypeEnum), nullable=False)
    recorded_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), primary_key=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class BiosignalMatrics(BiosignalBase):
    # BPM, temp, spo2, rr(rpm)
    __tablename__ = "biosignal_metrics"
    __table_args__ = {"schema": "biosignal"}

    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    matric_type: Mapped[Enum] = mapped_column(Enum(MatricTypeEnum), nullable=False, primary_key=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False,
                                                  primary_key=True)
    value : Mapped[float] = mapped_column(Float, nullable=False)

class BioMatrics(BiosignalBase):
    __tablename__ = "bio_metrics"
    __table_args__ = {"schema": "biosignal"}

    matrix_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7, nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    hr: Mapped[float] = mapped_column(Float, nullable=True)
    rr: Mapped[float] = mapped_column(Float, nullable=True)
    temp: Mapped[float] = mapped_column(Float, nullable=True)
    spo2: Mapped[float] = mapped_column(Float, nullable=True)

    recorded_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), primary_key=True)

class BPInitLog(BiosignalBase):
    __tablename__ = "bp_init_log"
    __table_args__ = {"schema": "biosignal"}

    log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)

    pttf: Mapped[float] = mapped_column(Float, nullable=False)
    pttd: Mapped[float] = mapped_column(Float, nullable=False)
    dPtt: Mapped[float] = mapped_column(Float, nullable=False)
    dPttNorm: Mapped[float] = mapped_column(Float, nullable=False)

    upSlope: Mapped[float] = mapped_column(Float, nullable=False)
    pw50: Mapped[float] = mapped_column(Float, nullable=False)
    diaSlope: Mapped[float] = mapped_column(Float, nullable=False)
    auc: Mapped[float] = mapped_column(Float, nullable=False)
    acdc: Mapped[float] = mapped_column(Float, nullable=False)

    # HRV & Quality (2)
    rrMean: Mapped[float] = mapped_column(Float, nullable=False)
    rrStd: Mapped[float] = mapped_column(Float, nullable=False)

    corrMean: Mapped[float] = mapped_column(Float, nullable=True)
    keepRatio: Mapped[float] = mapped_column(Float, nullable=True)

    # BaseValue (2)
    baseSBP: Mapped[float] = mapped_column(Float, nullable=False)
    baseDBP: Mapped[float] = mapped_column(Float, nullable=False)

    started_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    ended_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

class BPMeasureLog(BiosignalBase):
    __tablename__ = "bp_measure_log"
    __table_args__ = {"schema": "biosignal"}

    log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    base_sbp: Mapped[float] = mapped_column(Float, nullable=False)
    base_dbp: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_sbp: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_dbp: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    ended_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

