import enum


class BiosignalTypeEnum(enum.Enum):
    ECG = "ECG"
    PPG = "PPG"
    RESP = "RESP"


class MatricTypeEnum(enum.Enum):
    BPM = "BPM"
    BP = "BP"
    HR = "HR"
    RR = "RR"
    TEMP = "TEMP"
    SPO2 = "SPO2"