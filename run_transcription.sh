#!/bin/bash
# Start the local transcription server (Whisper + pyannote)
# Run this from the project root: ./run_transcription.sh
# First run: automatically creates venv and installs dependencies (~10 min)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/transcription/.venv"

# First-time setup: create venv and install dependencies
if [ ! -f "$VENV/bin/activate" ]; then
  echo "First-time setup: creating virtual environment..."
  python3 -m venv "$VENV"
  source "$VENV/bin/activate"
  echo "Installing dependencies (this takes ~10 minutes on first run)..."
  pip install --quiet -r transcription/requirements.txt
  echo "Setup complete."
  echo ""
else
  source "$VENV/bin/activate"
fi

echo "Starting Call Tracker local transcription server..."
echo "Server will be available at http://localhost:8001"
echo "Press Ctrl+C to stop."
echo ""

uvicorn transcription.main:app --host 0.0.0.0 --port 8001
