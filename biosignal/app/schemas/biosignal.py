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
    hr: int | None = None
    rr: int | None = None
    spo2: float | None = None
    temperature: float | None = None
    recorded_at: int

class BioMatricsAggregate(BaseModel):
    start_time: int
    end_time: int
    hr: int | None = None
    rr: int | None = None
    temp: float | None = None
    spo2: float | None = None

class BioMetricAggregate(BaseModel):
    start_time: int
    end_time: int
    value: float | None = None

class BPMeasureAggregate(BaseModel):
    start_time: int
    end_time: int
    recorded_at: int
    base_sbp: float
    base_dbp: float
    predicted_sbp: float
    predicted_dbp: float

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
