from pydantic import BaseModel
from datetime import datetime
import uuid


class UserRegisteredEvent(BaseModel):
    """User registration event schema"""
    event_type: str = "user.registered"
    username: str
    password: str
    practitioner_name: str
    rule: str | None = None
    department_id: str | None = None
    ward_id: str | None = None

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

class BiosignalECGPPGEvent(BaseModel):
    """Biosignal event schema (template for future use)"""
    event_type: str = "biosignal.ECG_PPG.received"
    patient_id: str
    ecg: list
    ppg: list | None = None
    timestamp: int

class BiosignalECGEvent(BaseModel):
    """Biosignal event schema (template for future use)"""
    event_type: str = "biosignal.ECG.received"
    patient_id: str
    signal_type: str
    signal: list
    timestamp: int

class BioMatrixEvent(BaseModel):
    """Biosignal event schema (template for future use)"""
    event_type: str = "biosignal.biomatrix.received"
    patient_id: str
    hr: int | None = None
    rr: int | None = None
    spo2: float | None = None
    temperature: float | None = None
    recorded_at: int

class BiosignalPPGEvent(BaseModel):
    """Biosignal event schema (template for future use)"""
    event_type: str = "biosignal.PPG.received"
    patient_id: str
    signal_type: str
    signal: list
    timestamp: int

class BiosignalRESPEvent(BaseModel):
    """Biosignal event schema (template for future use)"""
    event_type: str = "biosignal.RESP.received"
    patient_id: str
    signal_type: str
    signal: list
    timestamp: int

class BiosignalBPInitEvent(BaseModel):
    """Biosignal event schema (template for future use)"""
    event_type: str = "biosignal.BP.init"
    patient_id: str
    pttf: float
    pttd: float
    dPtt: float
    dPttNorm: float

    # Morphology (5)
    upSlope: float
    pw50: float
    diaSlope: float
    auc: float
    acdc: float

    # HRV & Quality (3)
    rrMean: float
    rrMean: float
    rrStd: float

    # BaseValue (2)
    baseSBP: float
    baseDBP: float

    corrMean: float
    keepRatio: float

    # 데이터 역 추적용 시간 값
    started_at: int
    ended_at: int


class BiosignalBPMeasuredEvent(BaseModel):
    event_type: str = "biosignal.BP.measured"
    patient_id: str
    base_sbp: float
    base_dbp: float
    predicted_sbp: float
    predicted_dbp: float
    started_at: int
    ended_at: int
    recorded_at: int


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
