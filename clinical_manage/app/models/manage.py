from sqlalchemy import String, UUID, TIMESTAMP
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
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("clinical_manage.patient_profile.patient_id", ondelete="CASCADE"), unique=True, nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


    __table_args__ = {"schema": "clinical_manage"}