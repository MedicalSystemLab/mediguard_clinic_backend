from fastapi import APIRouter
from .endpoints import admin_department, admin_patient, admin_practitioner, admin_ward, favorite, manage

api_router = APIRouter()
api_router.include_router(manage.router, prefix="/manage", tags=["manage"])
api_router.include_router(favorite.router, prefix="/favorite", tags=["favorite"])
api_router.include_router(
    admin_department.router,
    prefix="/manage/admin/departments",
    tags=["admin-departments"],
)
api_router.include_router(
    admin_practitioner.router,
    prefix="/manage/admin/practitioners",
    tags=["admin-practitioners"],
)
api_router.include_router(
    admin_patient.router,
    prefix="/manage/admin/patient",
    tags=["admin-patient"],
)
api_router.include_router(
    admin_ward.router,
    prefix="/manage/admin/wards",
    tags=["admin-wards"],
)
