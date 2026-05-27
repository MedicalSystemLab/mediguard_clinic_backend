from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
from .api.api import api_router
from .api.endpoints.monitoring_ws import start_monitoring_consumer, stop_monitoring_consumer
from common.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_monitoring_consumer()
    try:
        yield
    finally:
        await stop_monitoring_consumer()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_STR}{settings.API_V1_STR}/biosignal/openapi.json",
    lifespan=lifespan,
)


@app.get("/health", status_code=200)
def health_check_root():
    return {"status": "ok"}

api_router_root = APIRouter()


api_router_root.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(api_router_root, prefix=settings.API_STR)
