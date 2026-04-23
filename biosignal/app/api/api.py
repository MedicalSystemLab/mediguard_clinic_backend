from fastapi import APIRouter
from .endpoints import biosignals

api_router = APIRouter()

api_router.include_router(biosignals.router, prefix="/biosignals", tags=["biosignals"])