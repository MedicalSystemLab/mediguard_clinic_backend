#!/bin/bash
set -e

echo "Starting Mediguard Kafka Consumer Service..."

# Wait for Kafka to be ready
echo "Waiting for Kafka to be ready..."
sleep 10

# Run the consumer
exec python -m consumer.app.main
