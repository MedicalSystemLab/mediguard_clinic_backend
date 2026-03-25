import json
from typing import Any, Optional
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from common.core.config import settings

class KafkaProducerManager:
    def __init__(self):
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        if self._producer is None:
            import asyncio
            import aiokafka.errors
            
            max_retries = 5
            retry_delay = 5
            
            for attempt in range(max_retries):
                try:
                    self._producer = AIOKafkaProducer(
                        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                        value_serializer=lambda v: json.dumps(v).encode('utf-8')
                    )
                    await self._producer.start()
                    print(f"[KAFKA] Connected to {settings.KAFKA_BOOTSTRAP_SERVERS}")
                    return
                except (aiokafka.errors.KafkaConnectionError, aiokafka.errors.NoBrokersAvailable) as e:
                    print(f"[KAFKA] Connection attempt {attempt + 1} failed: {e}. Retrying in {retry_delay}s...")
                    self._producer = None
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                    else:
                        print(f"[KAFKA] All connection attempts to {settings.KAFKA_BOOTSTRAP_SERVERS} failed.")
                        raise e

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            self._producer = None

    async def send_event(self, topic: str, value: Any, key: str = None):
        if self._producer is None:
            await self.start()
        
        try:
            kafka_key = key.encode('utf-8') if key else None
            await self._producer.send_and_wait(topic, value, key=kafka_key)
        except Exception as e:
            # TODO: 로깅 시스템 구축 시 교체
            print(f"[KAFKA ERROR] Failed to send event to {topic}: {e}")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

class KafkaConsumerManager:
    def __init__(self, topic: str, group_id: str):
        self.topic = topic
        self.group_id = group_id
        self.consumer: Optional[AIOKafkaConsumer] = None

    async def start(self):
        if self.consumer:
            return
        
        import asyncio
        import aiokafka.errors

        max_retries = 5
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                self.consumer = AIOKafkaConsumer(
                    self.topic,
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    group_id=self.group_id,
                    value_deserializer=lambda v: json.loads(v.decode('utf-8'))
                )
                await self.consumer.start()
                print(f"[KAFKA] Consumer connected to {settings.KAFKA_BOOTSTRAP_SERVERS} for topic {self.topic}")
                return
            except (aiokafka.errors.KafkaConnectionError, aiokafka.errors.NoBrokersAvailable) as e:
                print(f"[KAFKA] Consumer connection attempt {attempt + 1} failed: {e}. Retrying in {retry_delay}s...")
                self.consumer = None
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    print(f"[KAFKA] All consumer connection attempts to {settings.KAFKA_BOOTSTRAP_SERVERS} failed.")
                    raise e

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
            self.consumer = None

    async def consume(self, handler_func):
        if not self.consumer:
            await self.start()
        try:
            async for msg in self.consumer:
                await handler_func(msg.value)
        finally:
            await self.stop()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

kafka_producer = KafkaProducerManager()
