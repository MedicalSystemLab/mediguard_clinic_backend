from pydantic import BaseModel
from datetime import datetime
import uuid


class UserRegisteredEvent(BaseModel):
    """User registration event schema"""
    event_type: str = "user.registered"
    username: str
    password: str

class PatientRegisteredEvent(BaseModel):
    """Patient registration event schema"""
    event_type: str = "patient.registered"
    number: str
    name: str
    birth: str
    gender: str | None
    depart: str | None
    admitted_ward: str | None
    manage_practitioner: str | None

class BiosignalEvent(BaseModel):
    """Biosignal event schema (template for future use)"""
    event_type: str
    patient_id: str
    data: dict
    timestamp: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ClinicalEvent(BaseModel):
    """Clinical event schema (template for future use)"""
    event_type: str
    patient_id: str
    action: str
    data: dict
    timestamp: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
