import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import uvicorn
from fastapi import FastAPI

from common.core.config import settings
from common.core.kafka_consumer import KafkaConsumerManager, set_metrics_updater
from notification.app.api.devices import router as devices_router
from notification.app.api.health import increment_metric, router as health_router, update_metrics
from notification.app.handlers.biosignal_alert_handler import handle_biosignal_alert_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mediguard Notification Service",
    description="Kafka alert consumer and FCM notification service",
    version="1.0.0",
)
app.include_router(health_router, tags=["health"])
app.include_router(devices_router, tags=["devices"])


async def run_consumer() -> None:
    logger.info("Starting Kafka notification consumer...")
    set_metrics_updater(update_metrics, increment_metric)

    consumer_manager = KafkaConsumerManager(group_id="mediguard-notification-consumer-group")
    consumer_manager.register_handler("biosignal.biomatrix.received", handle_biosignal_alert_event)
    consumer_manager.register_handler("biosignal.BP.measured", handle_biosignal_alert_event)

    try:
        update_metrics("status", "running")
        await consumer_manager.start([settings.KAFKA_TOPIC_BIOSIGNAL])
    except KeyboardInterrupt:
        logger.info("Received shutdown signal...")
    except Exception as exc:
        logger.error("Notification consumer error: %s", exc, exc_info=True)
        update_metrics("status", "error")
        raise
    finally:
        update_metrics("status", "stopped")
        await consumer_manager.stop()


async def run_api_server() -> None:
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    await asyncio.gather(
        run_api_server(),
        run_consumer(),
        return_exceptions=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
