from pydantic import BaseModel, ConfigDict, Field
import uuid

class UserRegister(BaseModel):
    username: str
    password: str
    practitioner_name: str
    rule: str | None = None
    department_id: str | None = None
    ward_id: str | None = None



class PatientRegister(BaseModel):
    number: str
    name: str
    birth: str
    gender: str | None = "U"
    depart: str | None = None
    admitted_ward: str | None = None
    manage_practitioner: str | None = None

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_reset_password: bool = False

class PatientLogin(BaseModel):
    patient_number: str
    patient_password: str


class UserLogin(BaseModel):
    username: str
    password: str

class UserPasswordReset(BaseModel):
    password: str

class UserPasswordResetResponse(BaseModel):
    is_reset_password: bool

class FCMDeviceRegister(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fcm_token: str = Field(min_length=1, alias="fcmToken")
    platform: str | None = None

class FCMDeviceRegisterResponse(BaseModel):
    registered: bool

class UserLogout(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fcm_token: str = Field(min_length=1, alias="fcmToken")

class UserLogoutResponse(BaseModel):
    logged_out: bool

class PatientLogin(BaseModel):
    patient_number: str
    patient_password: str

class UserBase(BaseModel):
    user_id: uuid.UUID

    class Config:
        from_attributes = True

class PatientBase(BaseModel):
    patient_id: uuid.UUID

    class Config:
        from_attributes = True


class UserMeResponse(UserBase):
    permissions: str

class User(UserBase):
    pass

class Patient(PatientBase):
    pass
