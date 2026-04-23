import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI
import uvicorn

from common.core.kafka_consumer import KafkaConsumerManager, set_metrics_updater
from consumer_db.app.handlers.auth_handler import handle_user_registered, handle_patient_registered
from consumer_db.app.handlers.biosignal_handler import handle_ecg_event, handle_ppg_event, handle_resp_event
from consumer_db.app.handlers.clinical_handler import handle_clinical_event
from consumer_db.app.api.health import router as health_router, update_metrics, increment_metric
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
    title="Mediguard DB Consumer Service",
    description="Kafka DB Consumer Service with Health Check API",
    version="1.0.0"
)

# Include health check router
app.include_router(health_router, tags=["health"])


async def run_consumer():
    """Run Kafka Consumer"""
    logger.info("Starting Kafka DB Consumer...")
    logger.info(f"Kafka Bootstrap Servers: {settings.KAFKA_BOOTSTRAP_SERVERS}")

    # Set metrics updater for kafka consumer
    set_metrics_updater(update_metrics, increment_metric)

    # Initialize consumer manager
    consumer_manager = KafkaConsumerManager(group_id="mediguard-db-consumer-group")

    # Register event handlers
    consumer_manager.register_handler("user.registered", handle_user_registered)
    consumer_manager.register_handler("patient.registered", handle_patient_registered)
    # Add more handlers as needed
    consumer_manager.register_handler("biosignal.ECG.received", handle_ecg_event)
    consumer_manager.register_handler("biosignal.PPG.received", handle_ppg_event)
    consumer_manager.register_handler("biosignal.RESP.received", handle_reso_event)
    # consumer_manager.register_handler("clinical.update", handle_clinical_event)

    # Subscribe to topics
    topics = [
        settings.KAFKA_TOPIC_AUTH,
        settings.KAFKA_TOPIC_BIOSIGNAL
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
        logger.info("DB Consumer service stopped")


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
    logger.info("Starting Mediguard DB Consumer Service...")

    # Run both FastAPI and Kafka Consumer concurrently
    await asyncio.gather(
        run_api_server(),
        run_consumer(),
        return_exceptions=True
    )


if __name__ == "__main__":
    asyncio.run(main())
