from pydantic import BaseModel
import uuid

class Register(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class PatientLogin(BaseModel):
    patient_number: str


class Login(BaseModel):
    username: str
    password: str


class RefreshToken(BaseModel):
    refresh_token: str

class UserBase(BaseModel):
    user_id: uuid.UUID

    class Config:
        from_attributes = True

class User(UserBase):
    pass
