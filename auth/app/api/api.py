from fastapi import APIRouter
from .endpoints import auth
from .endpoints import user
from .endpoints import patient

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(patient.router, prefix="/auth/patient", tags=["patient"])
api_router.include_router(user.router, prefix="/auth/user", tags=["user"])