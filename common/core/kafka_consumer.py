import json
import logging
import asyncio
from typing import Callable, Dict
from datetime import datetime
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from common.core.config import settings

logger = logging.getLogger(__name__)

# Metrics update function (will be imported from health.py)
_metrics_update_fn = None


def set_metrics_updater(update_fn, increment_fn):
    """Set the metrics update functions"""
    global _metrics_update_fn, _metrics_increment_fn
    _metrics_update_fn = update_fn
    _metrics_increment_fn = increment_fn


class KafkaConsumerManager:
    """Kafka Consumer Manager for handling events"""

    def __init__(self, group_id: str = "mediguard-consumer-group"):
        self.group_id = group_id
        self.consumer = None
        self.handlers: Dict[str, Callable] = {}
        self.running = False

    def register_handler(self, event_type: str, handler: Callable):
        """
        Register a handler function for specific event type

        Args:
            event_type: Event type string (e.g., "user.registered")
            handler: Async function to handle the event
        """
        self.handlers[event_type] = handler
        logger.info(f"Registered handler for event type: {event_type}")

    async def start(self, topics: list[str]):
        """
        Start Kafka consumer and begin processing messages

        Args:
            topics: List of Kafka topics to subscribe
        """
        self.consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            auto_offset_reset='earliest',  # Start from beginning if no offset
            enable_auto_commit=False,  # Manual commit for reliability
            max_poll_records=10,
        )

        await self.consumer.start()
        logger.info(f"Kafka Consumer started: {settings.KAFKA_BOOTSTRAP_SERVERS}")
        logger.info(f"Subscribed to topics: {topics}")

        self.running = True
        await self._consume_messages()

    async def _consume_messages(self):
        """Internal method to consume and process messages"""
        try:
            async for message in self.consumer:
                try:
                    event_data = message.value
                    event_type = event_data.get('event_type')

                    logger.info(
                        f"Received message - Topic: {message.topic}, "
                        f"Partition: {message.partition}, Offset: {message.offset}, "
                        f"Event Type: {event_type}"
                    )

                    # Find and execute handler
                    handler = self.handlers.get(event_type)
                    if handler:
                        await handler(event_data)
                        await self.consumer.commit()
                        logger.info(f"Successfully processed event: {event_type}")

                        # Update metrics
                        if _metrics_increment_fn:
                            _metrics_increment_fn("events_processed")
                        if _metrics_update_fn:
                            _metrics_update_fn("last_event_time", datetime.utcnow().isoformat())
                    else:
                        logger.warning(f"No handler registered for event type: {event_type}")
                        await self.consumer.commit()  # Commit anyway to avoid reprocessing

                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    # Update error metrics
                    if _metrics_increment_fn:
                        _metrics_increment_fn("errors")
                    # Don't commit on error - message will be reprocessed

        except KafkaError as e:
            logger.error(f"Kafka error: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Stop Kafka consumer"""
        if self.consumer and self.running:
            await self.consumer.stop()
            self.running = False
            logger.info("Kafka Consumer stopped")
