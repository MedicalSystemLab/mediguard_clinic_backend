from fastapi import APIRouter
from .endpoints import biosignals, monitoring_ws

api_router = APIRouter()

api_router.include_router(biosignals.router, prefix="/biosignal", tags=["biosignal"])
api_router.include_router(monitoring_ws.router, prefix="/biosignal", tags=["biosignal-monitoring"])
