#!/bin/bash
set -e

echo "Starting Mediguard Kafka DB Consumer Service..."

# Wait for Kafka to be ready
echo "Waiting for Kafka to be ready..."
sleep 10

# Run the DB consumer
exec python -m consumer_db.app.main
