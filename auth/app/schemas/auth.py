from pydantic import BaseModel
import uuid

class UserRegister(BaseModel):
    username: str
    password: str

class PatientRegister(BaseModel):
    patient_number: str
    patient_name: str
    patient_password: str
    patient_sex: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class PatientLogin(BaseModel):
    patient_number: str
    patient_password: str


class UserLogin(BaseModel):
    username: str
    password: str

class PatientLogin(BaseModel):
    patient_number: str
    patient_password: str

class RefreshToken(BaseModel):
    refresh_token: str

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