from fastapi import APIRouter
from .endpoints import favorite, manage

api_router = APIRouter()
api_router.include_router(manage.router, prefix="/manage", tags=["manage"])
api_router.include_router(favorite.router, prefix="/favorite", tags=["favorite"])
