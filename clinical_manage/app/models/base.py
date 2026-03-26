# 각 서비스별로 필요한 경우 추가 설정을 하거나, 공통 Base를 그대로 사용합니다.
from sqlalchemy.orm import DeclarativeBase


class ClinicBase(DeclarativeBase):
    __abstract__ = True
    __schema__ = "clinical_manage"
