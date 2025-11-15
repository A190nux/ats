#!/bin/bash
# Start the ATS API server

set -e

# Configuration
API_KEY="${API_KEY:-test-key-123}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-1}"
QUEUE_DB="${QUEUE_DB:-./jobs.db}"
UPLOAD_DIR="${UPLOAD_DIR:-./cv_uploads}"

echo "================================"
echo "Starting ATS API Server"
echo "================================"
echo "API Key: $API_KEY"
echo "Host: $HOST"
echo "Port: $PORT"
echo "Workers: $WORKERS"
echo "Queue DB: $QUEUE_DB"
echo "Upload Dir: $UPLOAD_DIR"
echo ""
echo "Swagger UI: http://localhost:$PORT/docs"
echo "ReDoc: http://localhost:$PORT/redoc"
echo "================================"
echo ""

# Create upload directory if it doesn't exist
mkdir -p "$UPLOAD_DIR"

# Export environment variables
export API_KEY
export QUEUE_DB
export UPLOAD_DIR

# Start API server
uvicorn backend.api:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers "$WORKERS" \
  --reload
