from sqlalchemy import String, UUID, TIMESTAMP, UniqueConstraint, Integer
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from clinical_manage.app.models.base import ClinicBase
import uuid

class Manage(ClinicBase):
    __tablename__ = "manage"

    manage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=func.gen_random_uuid(),
        primary_key=True, default=uuid.uuid4, index=True)
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("clinical_manage.patient_profile.patient_id", ondelete="CASCADE"),
        index=True, nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


    __table_args__ = (
        UniqueConstraint("practitioner_id", "patient_id", name="uq_manage_practitioner_patient"),
        {"schema": "clinical_manage"},
    )


class FavoritePatient(ClinicBase):
    __tablename__ = "favorite_patient"

    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("clinical_manage.patient_profile.patient_id", ondelete="CASCADE"),
        primary_key=True, index=True, nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = {"schema": "clinical_manage"}

class AlertConfig(ClinicBase):
    __tablename__ = "alert_config"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("clinical_manage.patient_profile.patient_id", ondelete="CASCADE"),
        index=True, nullable=False)
    bpm_max: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    bpm_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    bpm_alert_paused_until: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    spo2_max: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    spo2_min: Mapped[int] = mapped_column(Integer, nullable=False, default=92)
    spo2_alert_paused_until: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    rr_max: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    rr_min: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    rr_alert_paused_until: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    bp_max: Mapped[int] = mapped_column(Integer, nullable=False, default=150)
    bp_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    bp_alert_paused_until: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    temp_max: Mapped[int] = mapped_column(Integer, nullable=False, default=38)
    temp_min: Mapped[int] = mapped_column(Integer, nullable=False, default=35)
    temp_alert_paused_until: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

