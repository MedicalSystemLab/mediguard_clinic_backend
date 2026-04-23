#!/bin/bash
set -e

echo "Starting Mediguard Kafka Analysis Consumer Service..."

# Wait for Kafka to be ready
echo "Waiting for Kafka to be ready..."
sleep 10

# Run the Faust analysis worker
exec faust -A consumer_analysis.app.main worker -l info
