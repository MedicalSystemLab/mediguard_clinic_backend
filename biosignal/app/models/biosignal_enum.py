import enum


class BiosignalTypeEnum(enum.Enum):
    ECG = "ECG" # electrocardiogram
    PPG = "PPG" # photoplethysmogram
    RESP = "RESP" # respiratory rate


class MatricTypeEnum(enum.Enum):
    BPM = "BPM" # beats per minute
    BP = "BP" # blood pressure
    HR = "HR" # heart rate
    RR = "RR" # respiratory rate
    TEMP = "TEMP" # temperature
    SPO2 = "SPO2" # spo2