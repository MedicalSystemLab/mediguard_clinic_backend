import uuid
import enum
from sqlalchemy import String, UUID, TIMESTAMP, Enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from auth.app.models.base import AuthBase

class AuthPermissionEnum(enum.Enum):
    administrator = "administrator"
    practitioner = "practitioner"


class User(AuthBase):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=func.gen_random_uuid(),
        primary_key=True, default=uuid.uuid4, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    permissions : Mapped[Enum] = mapped_column(Enum(AuthPermissionEnum), nullable=False, default=AuthPermissionEnum.practitioner)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    activated_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = {"schema": "auth"}


class Patient(AuthBase):
    __tablename__ = "patient"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=func.gen_random_uuid(),
        primary_key=True, default=uuid.uuid4, index=True)
    patient_number: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    activated_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = {"schema": "auth"}