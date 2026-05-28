from fastapi import APIRouter
from .endpoints import admin_practitioner, favorite, manage

api_router = APIRouter()
api_router.include_router(manage.router, prefix="/manage", tags=["manage"])
api_router.include_router(favorite.router, prefix="/favorite", tags=["favorite"])
api_router.include_router(
    admin_practitioner.router,
    prefix="/admin/practitioners",
    tags=["admin-practitioners"],
)
