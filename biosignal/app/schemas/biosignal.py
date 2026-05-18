from pydantic import BaseModel

class ECGAndPPGSignal(BaseModel):
    ecg: list[int]
    ppg: list[int] | None = None
    recorded_at: int

class ECGBiosignal(BaseModel):
    signal: list[int]
    recorded_at: int

class PPGBiosignal(BaseModel):
    signal: list[int]
    recorded_at: int

class RESPBiosignal(BaseModel):
    signal: list[float]
    recorded_at: int

class BioMatrics(BaseModel):
    hr: float
    rr: float
    spo2: float | None = None
    temperature: float
    recorded_at: int

class BPAnalysisInitParams(BaseModel):
    # Base Timing (4)
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

    # HRV & Quality (2)
    rrMean: float
    rrStd: float

    # BaseValue (2)
    baseSBP: float
    baseDBP: float

    # 데이터 역추적을 위한 데이터의 시작과 끝 시간
    started_at: int
    ended_at: int