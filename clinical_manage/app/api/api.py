from fastapi import APIRouter
from .endpoints import manage

api_router = APIRouter()
api_router.include_router(manage.router, prefix="/manage", tags=["manage"])