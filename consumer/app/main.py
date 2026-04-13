import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI
import uvicorn

from consumer.app.core.kafka_consumer import KafkaConsumerManager, set_metrics_updater
from consumer.app.handlers.auth_handler import handle_user_registered
from consumer.app.handlers.biosignal_handler import handle_biosignal_event
from consumer.app.handlers.clinical_handler import handle_clinical_event
from consumer.app.api.health import router as health_router, update_metrics, increment_metric
from common.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Mediguard Consumer Service",
    description="Kafka Consumer Service with Health Check API",
    version="1.0.0"
)

# Include health check router
app.include_router(health_router, tags=["health"])


async def run_consumer():
    """Run Kafka Consumer"""
    logger.info("Starting Kafka Consumer...")
    logger.info(f"Kafka Bootstrap Servers: {settings.KAFKA_BOOTSTRAP_SERVERS}")

    # Set metrics updater for kafka consumer
    set_metrics_updater(update_metrics, increment_metric)

    # Initialize consumer manager
    consumer_manager = KafkaConsumerManager(group_id="mediguard-consumer-group")

    # Register event handlers
    consumer_manager.register_handler("user.registered", handle_user_registered)
    # Add more handlers as needed
    # consumer_manager.register_handler("biosignal.data", handle_biosignal_event)
    # consumer_manager.register_handler("clinical.update", handle_clinical_event)

    # Subscribe to topics
    topics = [
        settings.KAFKA_TOPIC_AUTH,
        # settings.KAFKA_TOPIC_BIOSIGNAL,  # Uncomment when ready
        # settings.KAFKA_TOPIC_USER,  # Uncomment when ready
    ]

    try:
        update_metrics("status", "running")
        await consumer_manager.start(topics)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal...")
    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)
        update_metrics("status", "error")
        raise
    finally:
        update_metrics("status", "stopped")
        await consumer_manager.stop()
        logger.info("Consumer service stopped")


async def run_api_server():
    """Run FastAPI server"""
    logger.info("Starting FastAPI Health Check Server on port 8000...")
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """Main entry point - runs both FastAPI and Kafka Consumer concurrently"""
    logger.info("Starting Mediguard Consumer Service...")

    # Run both FastAPI and Kafka Consumer concurrently
    await asyncio.gather(
        run_api_server(),
        run_consumer(),
        return_exceptions=True
    )


if __name__ == "__main__":
    asyncio.run(main())
