import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import faust
from common.core.config import settings

app = faust.App(
    "mediguard-analysis",
    broker=f"kafka://{settings.KAFKA_BOOTSTRAP_SERVERS}",
    consumer_group="mediguard-analysis-consumer-group",
    web_host="0.0.0.0",
    web_port=8001,
    topic_replication_factor=1,
    store="rocksdb://",
)

# Biosignal topic - raw JSON values
biosignal_topic = app.topic(
    settings.KAFKA_TOPIC_BIOSIGNAL,
    value_type=bytes,
    value_serializer="raw",
)

# Import agents to register them with the app
from consumer_analysis.app.agents import biosignal  # noqa: F401, E402
