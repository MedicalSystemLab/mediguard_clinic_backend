import json
import logging
from typing import Optional
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from common.core.config import settings

logger = logging.getLogger(__name__)


class KafkaProducerSingleton:
    """Singleton Kafka Producer for publishing events"""

    _instance: Optional[AIOKafkaProducer] = None
    _started: bool = False

    @classmethod
    async def get_producer(cls) -> AIOKafkaProducer:
        """Get or create Kafka producer instance"""
        if cls._instance is None:
            cls._instance = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                compression_type='gzip',
                acks='all',  # Wait for all replicas
                retries=3,
                max_in_flight_requests_per_connection=1,  # Ensure ordering
            )

        if not cls._started:
            await cls._instance.start()
            cls._started = True
            logger.info(f"Kafka Producer started: {settings.KAFKA_BOOTSTRAP_SERVERS}")

        return cls._instance

    @classmethod
    async def close(cls):
        """Close Kafka producer connection"""
        if cls._instance and cls._started:
            await cls._instance.stop()
            cls._started = False
            logger.info("Kafka Producer stopped")


async def publish_event(topic: str, event: dict, key: Optional[str] = None):
    """
    Publish an event to Kafka topic

    Args:
        topic: Kafka topic name
        event: Event data (dict, will be JSON serialized)
        key: Optional partition key
    """
    try:
        producer = await KafkaProducerSingleton.get_producer()
        await producer.send(topic, value=event, key=key)
        logger.info(f"Event published to topic '{topic}': {event.get('event_type', 'unknown')}")
    except KafkaError as e:
        logger.error(f"Failed to publish event to topic '{topic}': {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error publishing event: {e}")
        raise
