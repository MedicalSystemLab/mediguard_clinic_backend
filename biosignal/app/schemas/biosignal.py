from pydantic import BaseModel

class ECGBiosignal(BaseModel):
    signal: list[int]
    recorded_at: int

class PPGBiosignal(BaseModel):
    signal: list[int]
    recorded_at: int

class RESPBiosignal(BaseModel):
    signal: list[float]
    recorded_at: int
