from pydantic import BaseModel, EmailStr
import uuid

class Register(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class Login(BaseModel):
    email: EmailStr
    password: str


class RefreshToken(BaseModel):
    refresh_token: str


class ProfileSchema(BaseModel):
    user_id: uuid.UUID
    nickname: str | None = None
    job_role: str | None = None
    is_confined_worker: bool | None = False
    intensity_weight: float | None = 1.0
    height: float
    weight: float
    gender: bool | None = None
    birth_date: str | None = None

    class Config:
        from_attributes = True

class GoalSchema(BaseModel):
    user_id: uuid.UUID
    sleep_start : int
    sleep_end : int
    activate_bpm : int
    step_count : int
    step_distance_km : float
    total_calorie : int
    active_calorie : int

    class Config:
        from_attributes = True

class ProfileUpdate(BaseModel):
    nickname: str | None = None
    job_role: str | None = None
    is_confined_worker: bool | None = None
    intensity_weight: float | None = None
    height: float | None = None
    weight: float | None = None
    gender: bool | None = None
    birth_date: str | None = None

class GoalUpdate(BaseModel):
    sleep_start: int | None = None
    sleep_end: int | None = None
    activate_bpm: int | None = None
    step_count: int | None = None
    step_distance_km: float | None = None
    total_calorie: int | None = None
    active_calorie: int | None = None

class NicknameUpdate(BaseModel):
    nickname: str

class UserBase(BaseModel):
    user_id: uuid.UUID

    class Config:
        from_attributes = True

class User(UserBase):
    user_id : uuid.UUID
    email: str | None = None
    is_active: bool | None = None
