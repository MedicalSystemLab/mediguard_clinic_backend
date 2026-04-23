from fastapi import FastAPI, APIRouter
from .api.api import api_router
from common.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_STR}{settings.API_V1_STR}/biosignal/openapi.json"
)


@app.get("/health", status_code=200)
def health_check_root():
    return {"status": "ok"}

api_router_root = APIRouter()


api_router_root.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(api_router_root, prefix=settings.API_STR)

