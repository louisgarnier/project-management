#!/bin/bash
# Start the local transcription server (Whisper + pyannote)
# Run this from the project root: ./run_transcription.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting Call Tracker local transcription server..."
echo "Server will be available at http://localhost:8001"
echo "Press Ctrl+C to stop."
echo ""

# Activate venv if present
if [ -f "transcription/.venv/bin/activate" ]; then
  source transcription/.venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

uvicorn transcription.main:app --host 0.0.0.0 --port 8001
