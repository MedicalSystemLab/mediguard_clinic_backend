from sqlalchemy import String, UUID, TIMESTAMP, Boolean, Enum, Integer
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from clinical_manage.app.models.base import ClinicBase
import uuid
import enum

class GenderEnum(enum.Enum):
    M = "M"  # Male
    F = "F"  # Female
    U = "U"  # Unknown
    # 나중에 제3의 성별이나 '미선택'이 필요할 때 확장 용이

class PractitionerRoleEnum(enum.Enum):
    UNSPECIFIED = "UNSPECIFIED"  # 초기값/미지정
    GP = "GP"  # 일반의
    SPECIALIST = "SPECIALIST"  # 전문의
    RN = "RN"  # 간호사
    NP = "NP"  # 전문간호사
    TECHNICIAN = "TECHNICIAN"  # 의료기사
    OTHER = "OTHER"  # 기타

# class PractitionerProfiles(ClinicBase):
#     __tablename__ = "practitioner_profiles"
#
#     practitioner_id: Mapped[uuid.UUID] = mapped_column(
#         UUID(as_uuid=True), primary_key=True, nullable=False, index=True)
#     practitioner_name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
#     rule: Mapped[PractitionerRoleEnum] = mapped_column(Enum(PractitionerRoleEnum), nullable=False, default=PractitionerRoleEnum.UNSPECIFIED)
#     created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

class Ward(ClinicBase):
    __tablename__ = "ward"

    ward_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=func.gen_random_uuid(),
        primary_key=True, default=uuid.uuid4, index=True
    )
    ward_name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = {"schema": "clinical_manage"}

class Patient(ClinicBase):
    __tablename__ = "patient"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=func.gen_random_uuid(),
        primary_key=True, default=uuid.uuid4, index=True)
    patient_number: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    patient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sex : Mapped[GenderEnum] = mapped_column(Enum(GenderEnum), nullable=False, default=GenderEnum.U)
    age : Mapped[int] = mapped_column(Integer, nullable=False)
    is_admitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    admitted_ward_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("clinical_manage.ward.ward_id"), nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    discharged_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = {"schema": "clinical_manage"}