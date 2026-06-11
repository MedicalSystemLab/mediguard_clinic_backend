from fastapi import APIRouter, status

router = APIRouter()

consumer_metrics = {
    "status": "starting",
    "messages_processed": 0,
    "messages_failed": 0,
}


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {
        "status": "healthy",
        "service": "mediguard-notification",
        "consumer_status": consumer_metrics["status"],
    }


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def get_metrics():
    return consumer_metrics


def update_metrics(key: str, value):
    consumer_metrics[key] = value


def increment_metric(key: str):
    if key in consumer_metrics:
        consumer_metrics[key] += 1
