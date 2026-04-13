from fastapi import APIRouter, status
from datetime import datetime

router = APIRouter()

# Global metrics (will be updated by consumer)
consumer_metrics = {
    "status": "starting",
    "events_processed": 0,
    "last_event_time": None,
    "errors": 0,
    "start_time": datetime.utcnow().isoformat()
}


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint for monitoring consumer service status
    """
    return {
        "status": "ok",
        "service": "mediguard-consumer",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check():
    """
    Liveness probe - checks if the service is alive
    """
    return {
        "status": "alive",
        "service": "mediguard-consumer"
    }


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check():
    """
    Readiness probe - checks if the service is ready to process events
    """
    is_ready = consumer_metrics["status"] == "running"

    return {
        "status": "ready" if is_ready else "not_ready",
        "consumer_status": consumer_metrics["status"],
        "service": "mediguard-consumer"
    }


@router.get("/metrics", status_code=status.HTTP_200_OK)
async def get_metrics():
    """
    Get consumer metrics and statistics
    """
    return consumer_metrics


def update_metrics(key: str, value):
    """
    Update consumer metrics

    Args:
        key: Metric key to update
        value: New value
    """
    consumer_metrics[key] = value


def increment_metric(key: str):
    """
    Increment a counter metric

    Args:
        key: Metric key to increment
    """
    if key in consumer_metrics:
        consumer_metrics[key] += 1
