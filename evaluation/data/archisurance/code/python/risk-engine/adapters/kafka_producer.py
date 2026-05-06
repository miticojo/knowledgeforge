"""Kafka event producer -- Flow relationship to Apache Kafka (SystemSoftware).

Publishes risk evaluation events consumed by:
- Fraud Detection Engine (for pattern analysis)
- Data Warehouse (for analytics and reporting)
- Notification Service (for alerts on high-risk claims)
"""
import json
import logging

logger = logging.getLogger(__name__)


class KafkaEventProducer:
    """Adapter for Apache Kafka message broker (SystemSoftware).

    Flow: Risk Engine -> Apache Kafka -> [Fraud Detection, Data Warehouse, Notifications]
    Uses topic partitioning by claim_type for ordered processing.
    """

    def __init__(self, bootstrap_servers: str = "kafka.archisurance.internal:9092"):
        self.bootstrap_servers = bootstrap_servers
        self._producer = None

    async def publish(self, topic: str, event: dict):
        """Publish event to Kafka topic."""
        logger.info(f"Publishing to {topic}: {event.get('claim_id', 'unknown')}")
        # In production: confluent_kafka.Producer
        # For benchmark: skeleton only

    async def publish_batch(self, topic: str, events: list[dict]):
        """Batch publish for high-throughput scenarios."""
        for event in events:
            await self.publish(topic, event)
