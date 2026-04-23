from pydantic import BaseModel
import uuid

class UserRegister(BaseModel):
    username: str
    password: str
    practitioner_name: str



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

class PatientLogin(BaseModel):
    patient_number: str
    patient_password: str


class UserLogin(BaseModel):
    username: str
    password: str

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