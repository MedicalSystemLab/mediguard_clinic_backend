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
    __tablename__ = "biosignal_metrics"
    __table_args__ = {"schema": "biosignal"}

    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, nullable=False)
    matric_type: Mapped[Enum] = mapped_column(Enum(MatricTypeEnum), nullable=False, primary_key=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False,
                                                  primary_key=True)
    value : Mapped[float] = mapped_column(Float, nullable=False)




